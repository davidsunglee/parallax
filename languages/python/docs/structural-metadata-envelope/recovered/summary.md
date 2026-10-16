# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 90 | 0 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 5 | 10 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1446 | 0 | 0 | 0 |
| feature-boundary | non-authoritative | 3.13, 3.14 | 180 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3568.116 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-10-16T13:53:30.450783+00:00 | 3568.116 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-10-16T13:53:30.450910+00:00 | 2970.471 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-10-16T13:53:30.803003+00:00 | 0.054 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-10-16T13:53:30.857430+00:00 | 0.032 |
| setup | provisioner | member=snapshot-delivery | 2026-10-16T13:53:30.889639+00:00 | 2.545 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-10-16T13:53:33.437608+00:00 | 128.184 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-10-16T13:53:33.437622+00:00 | 3.144 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-10-16T13:53:52.045461+00:00 | 35.629 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-10-16T13:55:41.622011+00:00 | 120.226 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-10-16T13:55:41.622052+00:00 | 3.259 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-10-16T13:56:01.920934+00:00 | 30.030 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-10-16T13:57:41.848984+00:00 | 92.900 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-10-16T13:57:41.849026+00:00 | 0.790 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-10-16T13:58:00.609902+00:00 | 5.800 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-10-16T13:59:14.749479+00:00 | 68.020 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-10-16T13:59:14.749516+00:00 | 0.149 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-10-16T13:59:29.491172+00:00 | 1.035 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-10-16T14:00:22.770263+00:00 | 68.098 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-10-16T14:00:22.770304+00:00 | 0.149 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-10-16T14:00:37.440305+00:00 | 1.028 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-10-16T14:01:30.868168+00:00 | 9.803 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-10-16T14:01:40.671434+00:00 | 10.142 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-10-16T14:01:50.813701+00:00 | 189.032 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-10-16T14:04:59.843093+00:00 | 16.791 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-10-16T14:05:16.634272+00:00 | 148.021 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:07:44.658051+00:00 | 116.260 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-10-16T14:07:44.658078+00:00 | 3.148 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-10-16T14:08:03.560103+00:00 | 30.177 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:09:40.918865+00:00 | 123.931 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-10-16T14:09:40.918906+00:00 | 3.161 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-10-16T14:10:01.110224+00:00 | 30.386 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:11:44.850241+00:00 | 99.909 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-10-16T14:11:44.850281+00:00 | 0.897 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-10-16T14:12:03.943589+00:00 | 5.787 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:13:24.759877+00:00 | 80.341 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-10-16T14:13:24.759922+00:00 | 0.141 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-10-16T14:13:39.908154+00:00 | 1.006 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:14:45.101241+00:00 | 78.340 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-10-16T14:14:45.101285+00:00 | 0.250 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-10-16T14:15:00.841744+00:00 | 1.073 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:16:03.441178+00:00 | 7.555 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:16:10.996512+00:00 | 7.891 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:16:18.888231+00:00 | 161.053 |
| workload | leaf | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:18:59.941447+00:00 | 1287.943 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:40:27.890313+00:00 | 15.357 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-10-16T14:40:43.247052+00:00 | 137.233 |
| setup | close | member=snapshot-delivery | 2026-10-16T14:43:00.550690+00:00 | 0.179 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-10-16T14:43:00.957358+00:00 | 12.331 |
| member | instance-state | member=instance-state | 2026-10-16T14:43:13.291529+00:00 | 14.012 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-10-16T14:43:13.528401+00:00 | 0.094 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-10-16T14:43:13.622534+00:00 | 0.029 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-10-16T14:43:13.651535+00:00 | 0.917 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-10-16T14:43:14.569027+00:00 | 1.026 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-10-16T14:43:15.595050+00:00 | 1.707 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-10-16T14:43:17.301746+00:00 | 0.907 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-10-16T14:43:18.208839+00:00 | 0.848 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-10-16T14:43:19.057327+00:00 | 0.869 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-10-16T14:43:19.925916+00:00 | 0.752 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-10-16T14:43:20.678034+00:00 | 0.794 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-10-16T14:43:21.471657+00:00 | 0.954 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-10-16T14:43:22.426192+00:00 | 1.587 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-10-16T14:43:24.012804+00:00 | 0.849 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-10-16T14:43:24.862284+00:00 | 0.812 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-10-16T14:43:25.674384+00:00 | 0.816 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-10-16T14:43:26.489974+00:00 | 0.725 |
| member | write-lowering | member=write-lowering | 2026-10-16T14:43:27.315622+00:00 | 549.874 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-10-16T14:43:27.695801+00:00 | 0.066 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-10-16T14:43:27.762352+00:00 | 0.027 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:27.790112+00:00 | 0.887 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:28.677149+00:00 | 1.081 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:29.757748+00:00 | 0.888 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:30.645296+00:00 | 0.977 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:31.622447+00:00 | 1.153 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:32.775939+00:00 | 0.829 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:33.604578+00:00 | 1.003 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:34.607853+00:00 | 0.877 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:35.484546+00:00 | 0.920 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:36.404778+00:00 | 1.119 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:37.523514+00:00 | 0.818 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:38.341293+00:00 | 1.045 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:39.386501+00:00 | 0.867 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:40.253762+00:00 | 0.957 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:41.211072+00:00 | 1.143 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:42.353624+00:00 | 0.810 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:43.163704+00:00 | 1.032 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:44.195337+00:00 | 0.872 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:45.067844+00:00 | 0.929 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:45.997016+00:00 | 1.107 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:47.103604+00:00 | 0.815 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:47.918750+00:00 | 0.817 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:48.735608+00:00 | 0.850 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:49.585581+00:00 | 0.844 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:50.429504+00:00 | 0.899 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:51.328054+00:00 | 0.913 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:52.241131+00:00 | 0.786 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:53.027040+00:00 | 0.815 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:53.841597+00:00 | 0.889 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:54.730824+00:00 | 0.887 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:55.617660+00:00 | 1.150 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:56.768019+00:00 | 1.171 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:57.938758+00:00 | 0.904 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:58.842953+00:00 | 0.940 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:43:59.783369+00:00 | 1.301 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:01.084138+00:00 | 1.306 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:02.390347+00:00 | 0.880 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:03.270521+00:00 | 0.897 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:04.167913+00:00 | 1.023 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:05.190457+00:00 | 1.022 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:06.212812+00:00 | 1.132 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:07.344906+00:00 | 1.080 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:08.425266+00:00 | 1.489 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:09.914426+00:00 | 1.379 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:11.293392+00:00 | 1.093 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:12.385933+00:00 | 1.052 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:13.437499+00:00 | 1.079 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:14.516232+00:00 | 1.061 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:15.577146+00:00 | 1.045 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:16.622427+00:00 | 1.045 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:17.667130+00:00 | 1.057 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:18.723675+00:00 | 1.051 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:19.775103+00:00 | 1.154 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:20.929171+00:00 | 1.169 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:22.098433+00:00 | 1.153 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:23.251921+00:00 | 1.150 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:24.401815+00:00 | 1.166 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-16T14:44:25.567554+00:00 | 1.148 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-16T14:44:26.715933+00:00 | 1.099 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-16T14:44:27.814643+00:00 | 1.711 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-16T14:44:29.525616+00:00 | 4.139 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-16T14:44:33.664735+00:00 | 1.109 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-16T14:44:34.773484+00:00 | 1.735 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-16T14:44:36.508757+00:00 | 4.237 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-10-16T14:44:40.745507+00:00 | 0.808 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-16T14:44:41.553705+00:00 | 5.027 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-16T14:44:46.580904+00:00 | 1.058 |
| case | predicate-flush.reaching.objects-128.columns | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-16T14:44:47.639240+00:00 | 37.671 |
| case | predicate-flush.reaching.objects-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-16T14:45:25.310372+00:00 | 36.346 |
| case | predicate-flush.unchanged.objects-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-16T14:46:01.656652+00:00 | 17.904 |
| case | predicate-flush.wide.history-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-16T14:46:19.560619+00:00 | 12.558 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:32.118742+00:00 | 0.807 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:32.925462+00:00 | 1.022 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:33.947906+00:00 | 0.859 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:34.807032+00:00 | 0.948 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:35.754712+00:00 | 1.096 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:36.850453+00:00 | 0.814 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:37.664150+00:00 | 0.983 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:38.647150+00:00 | 0.859 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:39.505761+00:00 | 0.906 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:40.412158+00:00 | 1.080 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:41.491991+00:00 | 0.808 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:42.300103+00:00 | 0.999 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:43.299251+00:00 | 0.849 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:44.148494+00:00 | 0.954 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:45.102563+00:00 | 1.104 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:46.206462+00:00 | 0.891 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:47.097657+00:00 | 1.013 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:48.110359+00:00 | 0.872 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:48.982273+00:00 | 0.943 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:49.925743+00:00 | 1.091 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:51.016826+00:00 | 0.843 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:51.859677+00:00 | 0.833 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:52.692912+00:00 | 0.872 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:53.564639+00:00 | 0.854 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:54.418676+00:00 | 0.901 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:55.319665+00:00 | 0.910 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:56.229667+00:00 | 0.808 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:57.038112+00:00 | 0.813 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:57.851386+00:00 | 0.883 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:58.733977+00:00 | 0.911 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:46:59.644857+00:00 | 1.143 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:00.788336+00:00 | 1.130 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:01.918750+00:00 | 0.907 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:02.825752+00:00 | 0.911 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:03.737094+00:00 | 1.228 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:04.964718+00:00 | 1.249 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:06.213445+00:00 | 0.894 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:07.107245+00:00 | 0.881 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:07.987819+00:00 | 1.015 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:09.002466+00:00 | 1.001 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:10.003360+00:00 | 1.090 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:11.093049+00:00 | 1.083 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:12.176312+00:00 | 1.439 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:13.614907+00:00 | 1.545 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:15.159562+00:00 | 1.088 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:16.247787+00:00 | 1.039 |
| case | leaf.string.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:17.286634+00:00 | 1.464 |
| case | leaf.string.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:18.750258+00:00 | 1.458 |
| case | leaf.boolean.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:20.208456+00:00 | 1.070 |
| case | leaf.boolean.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:21.278893+00:00 | 1.164 |
| case | leaf.boolean.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:22.443333+00:00 | 1.075 |
| case | leaf.boolean.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:23.518712+00:00 | 1.157 |
| case | leaf.int32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:24.676216+00:00 | 1.165 |
| case | leaf.int32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:25.840982+00:00 | 1.419 |
| case | leaf.int32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:27.260119+00:00 | 1.141 |
| case | leaf.int32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:28.400978+00:00 | 1.401 |
| case | leaf.int64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:29.801956+00:00 | 1.187 |
| case | leaf.int64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:30.989221+00:00 | 1.424 |
| case | leaf.int64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:32.412847+00:00 | 1.193 |
| case | leaf.int64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:33.605724+00:00 | 1.337 |
| case | leaf.float32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:34.943190+00:00 | 1.654 |
| case | leaf.float32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:36.597217+00:00 | 2.209 |
| case | leaf.float32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:38.805876+00:00 | 1.686 |
| case | leaf.float32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:40.492163+00:00 | 2.174 |
| case | leaf.float64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:42.666454+00:00 | 1.201 |
| case | leaf.float64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:43.867647+00:00 | 1.358 |
| case | leaf.float64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:45.225546+00:00 | 1.213 |
| case | leaf.float64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:46.438976+00:00 | 1.330 |
| case | leaf.decimal.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:47.769138+00:00 | 2.005 |
| case | leaf.decimal.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:49.774544+00:00 | 3.446 |
| case | leaf.decimal.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:53.220237+00:00 | 2.012 |
| case | leaf.decimal.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:55.231917+00:00 | 3.449 |
| case | leaf.bytes.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:58.681167+00:00 | 1.222 |
| case | leaf.bytes.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:47:59.903426+00:00 | 1.475 |
| case | leaf.bytes.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:01.378462+00:00 | 1.200 |
| case | leaf.bytes.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:02.578976+00:00 | 1.455 |
| case | leaf.date.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:04.034186+00:00 | 1.296 |
| case | leaf.date.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:05.329993+00:00 | 1.739 |
| case | leaf.date.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:07.069446+00:00 | 1.323 |
| case | leaf.date.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:08.392029+00:00 | 1.760 |
| case | leaf.time.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:10.152133+00:00 | 1.353 |
| case | leaf.time.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:11.504889+00:00 | 1.734 |
| case | leaf.time.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:13.239319+00:00 | 1.358 |
| case | leaf.time.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:14.596982+00:00 | 1.765 |
| case | leaf.timestamp.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:16.361944+00:00 | 2.088 |
| case | leaf.timestamp.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:18.449858+00:00 | 3.307 |
| case | leaf.timestamp.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:21.756424+00:00 | 2.098 |
| case | leaf.timestamp.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:23.854348+00:00 | 3.341 |
| case | leaf.uuid.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:27.195802+00:00 | 1.850 |
| case | leaf.uuid.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:29.045950+00:00 | 2.575 |
| case | leaf.uuid.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:31.620987+00:00 | 1.855 |
| case | leaf.uuid.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:33.476508+00:00 | 2.463 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:35.939284+00:00 | 0.990 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:36.929628+00:00 | 1.027 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:37.956495+00:00 | 0.992 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:38.948331+00:00 | 1.007 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:39.955531+00:00 | 1.018 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:40.973689+00:00 | 1.002 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:41.976132+00:00 | 1.093 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:43.069033+00:00 | 1.103 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:44.171691+00:00 | 1.106 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:45.277799+00:00 | 1.144 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:46.422241+00:00 | 1.118 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-16T14:48:47.539925+00:00 | 1.090 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:48:48.629479+00:00 | 1.039 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:48:49.668563+00:00 | 1.543 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:48:51.211267+00:00 | 3.595 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:48:54.806027+00:00 | 1.041 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:48:55.847015+00:00 | 1.558 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:48:57.404701+00:00 | 3.704 |
| case | leaf-acquisition.string.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:01.108739+00:00 | 2.030 |
| case | leaf-acquisition.string.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:03.138962+00:00 | 2.027 |
| case | leaf-acquisition.boolean.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:05.165812+00:00 | 1.376 |
| case | leaf-acquisition.boolean.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:06.542311+00:00 | 1.396 |
| case | leaf-acquisition.int32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:07.938374+00:00 | 1.915 |
| case | leaf-acquisition.int32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:09.853697+00:00 | 1.864 |
| case | leaf-acquisition.int64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:11.717484+00:00 | 2.056 |
| case | leaf-acquisition.int64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:13.773140+00:00 | 2.098 |
| case | leaf-acquisition.float32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:15.871309+00:00 | 6.707 |
| case | leaf-acquisition.float32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:22.578486+00:00 | 6.405 |
| case | leaf-acquisition.float64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:28.983691+00:00 | 2.840 |
| case | leaf-acquisition.float64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:31.823752+00:00 | 2.768 |
| case | leaf-acquisition.decimal.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:34.592105+00:00 | 9.694 |
| case | leaf-acquisition.decimal.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:44.286195+00:00 | 9.633 |
| case | leaf-acquisition.bytes.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:53.919268+00:00 | 3.573 |
| case | leaf-acquisition.bytes.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:49:57.492224+00:00 | 3.590 |
| case | leaf-acquisition.date.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:01.082744+00:00 | 4.675 |
| case | leaf-acquisition.date.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:05.758086+00:00 | 4.760 |
| case | leaf-acquisition.time.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:10.517794+00:00 | 6.003 |
| case | leaf-acquisition.time.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:16.520953+00:00 | 5.853 |
| case | leaf-acquisition.timestamp.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:22.374139+00:00 | 14.819 |
| case | leaf-acquisition.timestamp.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:37.193454+00:00 | 14.701 |
| case | leaf-acquisition.uuid.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:51.894463+00:00 | 5.003 |
| case | leaf-acquisition.uuid.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-16T14:50:56.897928+00:00 | 4.988 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-10-16T14:51:01.885941+00:00 | 0.802 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-16T14:51:02.687610+00:00 | 4.092 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-16T14:51:06.779900+00:00 | 0.981 |
| case | predicate-flush.reaching.objects-128.columns | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-16T14:51:07.760790+00:00 | 32.679 |
| case | predicate-flush.reaching.objects-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-16T14:51:40.440203+00:00 | 30.719 |
| case | predicate-flush.unchanged.objects-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-16T14:52:11.159316+00:00 | 15.162 |
| case | predicate-flush.wide.history-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-16T14:52:26.321167+00:00 | 10.723 |
| member | feature-boundary | member=feature-boundary | 2026-10-16T14:52:37.232103+00:00 | 21.335 |
| setup | identity | member=feature-boundary, runtime=3.13 | 2026-10-16T14:52:37.459144+00:00 | 0.069 |
| setup | identity | member=feature-boundary, runtime=3.14 | 2026-10-16T14:52:37.527862+00:00 | 0.028 |
| case | predicate.shallow-scalar.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-16T14:52:37.556292+00:00 | 0.325 |
| case | predicate.shallow-scalar.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-16T14:52:37.881441+00:00 | 0.401 |
| case | predicate.scalar-any.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-16T14:52:38.282866+00:00 | 0.300 |
| case | predicate.scalar-any.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-16T14:52:38.583346+00:00 | 0.410 |
| case | predicate.nested-all.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-16T14:52:38.993633+00:00 | 0.304 |
| case | predicate.nested-all.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-16T14:52:39.297902+00:00 | 0.426 |
| case | predicate.two-hop-to-one.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-16T14:52:39.723734+00:00 | 0.310 |
| case | predicate.two-hop-to-one.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-16T14:52:40.033446+00:00 | 0.434 |
| case | predicate.quantifier-through-to-one.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-16T14:52:40.467738+00:00 | 0.309 |
| case | predicate.quantifier-through-to-one.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-16T14:52:40.776628+00:00 | 0.440 |
| case | predicate.subtype-narrowing.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-16T14:52:41.216773+00:00 | 0.315 |
| case | predicate.subtype-narrowing.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-16T14:52:41.531896+00:00 | 0.440 |
| case | scalar-collection.integer.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:41.971546+00:00 | 0.292 |
| case | scalar-collection.integer.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:42.263664+00:00 | 0.294 |
| case | scalar-collection.integer.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:42.557353+00:00 | 0.299 |
| case | scalar-collection.integer.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:42.856066+00:00 | 0.300 |
| case | scalar-collection.integer.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:43.156135+00:00 | 0.340 |
| case | scalar-collection.integer.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:43.496024+00:00 | 0.325 |
| case | scalar-collection.string.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:43.820644+00:00 | 0.291 |
| case | scalar-collection.string.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:44.111962+00:00 | 0.292 |
| case | scalar-collection.string.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:44.404485+00:00 | 0.296 |
| case | scalar-collection.string.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:44.700903+00:00 | 0.292 |
| case | scalar-collection.string.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:44.993351+00:00 | 0.373 |
| case | scalar-collection.string.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:45.366888+00:00 | 0.298 |
| case | scalar-collection.decimal.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:45.665391+00:00 | 0.293 |
| case | scalar-collection.decimal.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:45.958274+00:00 | 0.294 |
| case | scalar-collection.decimal.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:46.251831+00:00 | 0.319 |
| case | scalar-collection.decimal.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:46.571298+00:00 | 0.336 |
| case | scalar-collection.decimal.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-16T14:52:46.907454+00:00 | 0.692 |
| case | scalar-collection.decimal.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-16T14:52:47.599850+00:00 | 0.706 |
| case | predicate.shallow-scalar.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-16T14:52:48.305991+00:00 | 0.296 |
| case | predicate.shallow-scalar.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-16T14:52:48.601692+00:00 | 0.380 |
| case | predicate.scalar-any.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-16T14:52:48.981257+00:00 | 0.294 |
| case | predicate.scalar-any.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-16T14:52:49.275747+00:00 | 0.390 |
| case | predicate.nested-all.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-16T14:52:49.666204+00:00 | 0.296 |
| case | predicate.nested-all.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-16T14:52:49.962511+00:00 | 0.391 |
| case | predicate.two-hop-to-one.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-16T14:52:50.353920+00:00 | 0.301 |
| case | predicate.two-hop-to-one.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-16T14:52:50.654915+00:00 | 0.409 |
| case | predicate.quantifier-through-to-one.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-16T14:52:51.063922+00:00 | 0.299 |
| case | predicate.quantifier-through-to-one.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-16T14:52:51.363157+00:00 | 0.415 |
| case | predicate.subtype-narrowing.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-16T14:52:51.778654+00:00 | 0.298 |
| case | predicate.subtype-narrowing.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-16T14:52:52.076750+00:00 | 0.414 |
| case | scalar-collection.integer.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:52.490312+00:00 | 0.287 |
| case | scalar-collection.integer.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:52.777516+00:00 | 0.284 |
| case | scalar-collection.integer.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:53.061921+00:00 | 0.288 |
| case | scalar-collection.integer.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:53.350010+00:00 | 0.290 |
| case | scalar-collection.integer.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:53.640522+00:00 | 0.321 |
| case | scalar-collection.integer.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:53.961175+00:00 | 0.309 |
| case | scalar-collection.string.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:54.270666+00:00 | 0.284 |
| case | scalar-collection.string.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:54.554477+00:00 | 0.285 |
| case | scalar-collection.string.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:54.839749+00:00 | 0.287 |
| case | scalar-collection.string.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:55.126319+00:00 | 0.293 |
| case | scalar-collection.string.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:55.419370+00:00 | 0.354 |
| case | scalar-collection.string.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:55.773756+00:00 | 0.293 |
| case | scalar-collection.decimal.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:56.066847+00:00 | 0.286 |
| case | scalar-collection.decimal.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:56.353285+00:00 | 0.282 |
| case | scalar-collection.decimal.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:56.635257+00:00 | 0.306 |
| case | scalar-collection.decimal.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:56.941032+00:00 | 0.305 |
| case | scalar-collection.decimal.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-16T14:52:57.246117+00:00 | 0.613 |
| case | scalar-collection.decimal.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-16T14:52:57.858957+00:00 | 0.631 |
