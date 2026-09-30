# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 81 | 9 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 5 | 10 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1230 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3296.601 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-09-30T09:42:49.060417+00:00 | 3296.601 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-09-30T09:42:49.060549+00:00 | 2937.484 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:42:49.378156+00:00 | 0.439 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-09-30T09:42:49.817578+00:00 | 0.035 |
| setup | provisioner | member=snapshot-delivery | 2026-09-30T09:42:49.852811+00:00 | 3.182 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:42:53.047824+00:00 | 103.578 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-09-30T09:42:53.047836+00:00 | 3.219 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-09-30T09:43:11.219092+00:00 | 30.969 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:44:36.625814+00:00 | 111.045 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-09-30T09:44:36.625858+00:00 | 3.146 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-09-30T09:44:55.584114+00:00 | 30.064 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:46:27.671048+00:00 | 90.795 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-09-30T09:46:27.671083+00:00 | 0.627 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-09-30T09:46:45.709677+00:00 | 6.016 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:47:58.466153+00:00 | 66.929 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-09-30T09:47:58.466189+00:00 | 0.222 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-09-30T09:48:12.337465+00:00 | 1.142 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:49:05.395108+00:00 | 65.498 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-09-30T09:49:05.395143+00:00 | 0.253 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-09-30T09:49:19.252870+00:00 | 1.051 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:50:10.893449+00:00 | 10.681 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:50:21.574188+00:00 | 11.175 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:50:32.753220+00:00 | 184.056 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:53:36.808757+00:00 | 15.697 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-09-30T09:53:52.505571+00:00 | 144.493 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-09-30T09:56:17.000014+00:00 | 112.987 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-09-30T09:56:17.000043+00:00 | 3.162 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-09-30T09:56:35.739934+00:00 | 30.089 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-09-30T09:58:09.989584+00:00 | 124.601 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-09-30T09:58:09.989626+00:00 | 3.072 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-09-30T09:58:30.868191+00:00 | 30.384 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:00:14.595782+00:00 | 101.758 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-09-30T10:00:14.595821+00:00 | 0.961 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-09-30T10:00:34.004623+00:00 | 6.165 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:01:56.354035+00:00 | 76.380 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-09-30T10:01:56.354073+00:00 | 0.298 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-09-30T10:02:13.752318+00:00 | 1.474 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:03:12.734021+00:00 | 72.408 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-09-30T10:03:12.734065+00:00 | 0.240 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-09-30T10:03:27.799606+00:00 | 1.094 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:04:25.142271+00:00 | 8.861 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:04:34.003525+00:00 | 9.369 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:04:43.379649+00:00 | 167.188 |
| workload | leaf | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:07:30.567270+00:00 | 1297.556 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:29:08.123811+00:00 | 15.544 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-09-30T10:29:23.667552+00:00 | 142.318 |
| setup | close | member=snapshot-delivery | 2026-09-30T10:31:46.100190+00:00 | 0.228 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-09-30T10:31:46.599934+00:00 | 12.689 |
| member | instance-state | member=instance-state | 2026-09-30T10:31:59.295157+00:00 | 15.056 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-09-30T10:31:59.529941+00:00 | 0.478 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-09-30T10:32:00.008369+00:00 | 0.035 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-09-30T10:32:00.043305+00:00 | 1.216 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-09-30T10:32:01.258962+00:00 | 1.035 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-09-30T10:32:02.293700+00:00 | 1.642 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-09-30T10:32:03.935354+00:00 | 0.893 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-09-30T10:32:04.828384+00:00 | 0.837 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-09-30T10:32:05.665553+00:00 | 0.835 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-09-30T10:32:06.500251+00:00 | 0.755 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-09-30T10:32:07.255394+00:00 | 0.822 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-09-30T10:32:08.077458+00:00 | 1.059 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-09-30T10:32:09.136071+00:00 | 1.700 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-09-30T10:32:10.836094+00:00 | 0.922 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-09-30T10:32:11.757878+00:00 | 0.868 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-09-30T10:32:12.626128+00:00 | 0.862 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-09-30T10:32:13.487871+00:00 | 0.778 |
| member | write-lowering | member=write-lowering | 2026-09-30T10:32:14.368432+00:00 | 331.203 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-09-30T10:32:14.744335+00:00 | 0.313 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-09-30T10:32:15.057398+00:00 | 0.034 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:15.095291+00:00 | 1.142 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:16.237800+00:00 | 0.966 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:17.204151+00:00 | 0.872 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:18.075860+00:00 | 0.909 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:18.985197+00:00 | 1.066 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:20.051683+00:00 | 0.720 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:20.771458+00:00 | 0.920 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:21.691387+00:00 | 0.829 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:22.519986+00:00 | 0.861 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:23.381277+00:00 | 1.046 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:24.427644+00:00 | 0.717 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:25.144307+00:00 | 0.972 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:26.116681+00:00 | 0.859 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:26.975632+00:00 | 0.901 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:27.876562+00:00 | 1.059 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:28.935600+00:00 | 0.717 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:29.652497+00:00 | 0.928 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:30.580527+00:00 | 0.820 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:31.400504+00:00 | 0.856 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:32.256563+00:00 | 1.051 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:33.307116+00:00 | 0.731 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:34.038209+00:00 | 0.716 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:34.754357+00:00 | 0.751 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:35.504948+00:00 | 0.743 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:36.247983+00:00 | 0.798 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:37.045864+00:00 | 0.792 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:37.837599+00:00 | 0.693 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:38.530296+00:00 | 0.687 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:39.217644+00:00 | 0.778 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:39.996057+00:00 | 0.773 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:40.769311+00:00 | 1.021 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:41.790512+00:00 | 1.023 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:42.813733+00:00 | 0.802 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:43.615739+00:00 | 0.790 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:44.405851+00:00 | 1.159 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:45.564610+00:00 | 1.152 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:46.716752+00:00 | 0.773 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:47.489779+00:00 | 0.777 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:48.266561+00:00 | 0.972 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:49.238273+00:00 | 0.971 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:50.209751+00:00 | 1.154 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:51.364068+00:00 | 1.134 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:52.497899+00:00 | 1.987 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:54.485052+00:00 | 1.898 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:56.383355+00:00 | 1.151 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-30T10:32:57.534652+00:00 | 1.114 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-30T10:32:58.649136+00:00 | 1.094 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-30T10:32:59.742767+00:00 | 1.933 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-30T10:33:01.675409+00:00 | 5.246 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-30T10:33:06.921157+00:00 | 1.100 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-30T10:33:08.020984+00:00 | 1.957 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-30T10:33:09.978272+00:00 | 5.385 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-09-30T10:33:15.363485+00:00 | 0.708 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-09-30T10:33:16.071102+00:00 | 4.520 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-09-30T10:33:20.591351+00:00 | 0.930 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:21.525198+00:00 | 0.758 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:22.283616+00:00 | 0.993 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:23.277153+00:00 | 0.900 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:24.177198+00:00 | 0.948 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:25.125303+00:00 | 1.106 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:26.231471+00:00 | 0.757 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:26.988551+00:00 | 0.969 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:27.957875+00:00 | 0.876 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:28.833939+00:00 | 0.902 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:29.735961+00:00 | 1.089 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:30.825455+00:00 | 0.754 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:31.579948+00:00 | 0.986 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:32.565575+00:00 | 0.905 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:33.470613+00:00 | 0.947 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:34.417359+00:00 | 1.085 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:35.502523+00:00 | 0.761 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:36.263437+00:00 | 0.974 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:37.237719+00:00 | 0.866 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:38.103799+00:00 | 0.900 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:39.004260+00:00 | 1.064 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:40.068196+00:00 | 0.753 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:40.821418+00:00 | 0.752 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:41.573189+00:00 | 0.793 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:42.366317+00:00 | 0.784 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:43.150128+00:00 | 0.827 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:43.976680+00:00 | 0.833 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:44.809294+00:00 | 0.733 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:45.542630+00:00 | 0.735 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:46.277668+00:00 | 0.814 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:47.091309+00:00 | 0.808 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:47.898852+00:00 | 1.038 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:48.937345+00:00 | 1.031 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:49.968520+00:00 | 0.827 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:50.795217+00:00 | 0.820 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:51.615349+00:00 | 1.150 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:52.765270+00:00 | 1.156 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:53.921598+00:00 | 0.805 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:54.726757+00:00 | 0.802 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:55.529231+00:00 | 0.996 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:56.525410+00:00 | 0.997 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:57.522624+00:00 | 1.166 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:58.689082+00:00 | 1.139 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:33:59.828478+00:00 | 1.911 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:01.739951+00:00 | 1.827 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:03.566527+00:00 | 1.160 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:04.726323+00:00 | 1.113 |
| case | leaf.string.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:05.839642+00:00 | 1.368 |
| case | leaf.string.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:07.207660+00:00 | 1.372 |
| case | leaf.boolean.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:08.579921+00:00 | 1.006 |
| case | leaf.boolean.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:09.585808+00:00 | 1.088 |
| case | leaf.boolean.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:10.673949+00:00 | 1.002 |
| case | leaf.boolean.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:11.676437+00:00 | 1.089 |
| case | leaf.int32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:12.765709+00:00 | 1.057 |
| case | leaf.int32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:13.822576+00:00 | 1.276 |
| case | leaf.int32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:15.098222+00:00 | 1.059 |
| case | leaf.int32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:16.157615+00:00 | 1.266 |
| case | leaf.int64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:17.424090+00:00 | 1.075 |
| case | leaf.int64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:18.498973+00:00 | 1.313 |
| case | leaf.int64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:19.812114+00:00 | 1.063 |
| case | leaf.int64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:20.874906+00:00 | 1.296 |
| case | leaf.float32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:22.170935+00:00 | 1.584 |
| case | leaf.float32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:23.754847+00:00 | 2.088 |
| case | leaf.float32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:25.843031+00:00 | 1.605 |
| case | leaf.float32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:27.447724+00:00 | 2.112 |
| case | leaf.float64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:29.559792+00:00 | 1.170 |
| case | leaf.float64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:30.730084+00:00 | 1.305 |
| case | leaf.float64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:32.035281+00:00 | 1.188 |
| case | leaf.float64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:33.223637+00:00 | 1.310 |
| case | leaf.decimal.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:34.533921+00:00 | 1.916 |
| case | leaf.decimal.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:36.449843+00:00 | 3.408 |
| case | leaf.decimal.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:39.858187+00:00 | 1.915 |
| case | leaf.decimal.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:41.773265+00:00 | 3.436 |
| case | leaf.bytes.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:45.209240+00:00 | 1.168 |
| case | leaf.bytes.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:46.377035+00:00 | 1.436 |
| case | leaf.bytes.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:47.813369+00:00 | 1.179 |
| case | leaf.bytes.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:48.992495+00:00 | 1.443 |
| case | leaf.date.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:50.435397+00:00 | 1.272 |
| case | leaf.date.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:51.706993+00:00 | 1.677 |
| case | leaf.date.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:53.384190+00:00 | 1.267 |
| case | leaf.date.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:54.651577+00:00 | 1.705 |
| case | leaf.time.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:56.356387+00:00 | 1.301 |
| case | leaf.time.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:57.657776+00:00 | 1.704 |
| case | leaf.time.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:34:59.361918+00:00 | 1.300 |
| case | leaf.time.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:00.661702+00:00 | 1.722 |
| case | leaf.timestamp.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:02.383419+00:00 | 2.009 |
| case | leaf.timestamp.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:04.392574+00:00 | 3.302 |
| case | leaf.timestamp.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:07.694613+00:00 | 2.015 |
| case | leaf.timestamp.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:09.709762+00:00 | 3.277 |
| case | leaf.uuid.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:12.986464+00:00 | 1.839 |
| case | leaf.uuid.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:14.825321+00:00 | 2.412 |
| case | leaf.uuid.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:17.237515+00:00 | 1.843 |
| case | leaf.uuid.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-30T10:35:19.080921+00:00 | 2.419 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:21.500219+00:00 | 1.117 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:22.617304+00:00 | 1.873 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:24.490387+00:00 | 4.863 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:29.353330+00:00 | 1.119 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:30.471955+00:00 | 1.880 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:32.352433+00:00 | 4.989 |
| case | leaf-acquisition.string.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:37.340995+00:00 | 2.093 |
| case | leaf-acquisition.string.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:39.434438+00:00 | 2.076 |
| case | leaf-acquisition.boolean.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:41.510702+00:00 | 1.457 |
| case | leaf-acquisition.boolean.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:42.967913+00:00 | 1.469 |
| case | leaf-acquisition.int32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:44.436620+00:00 | 2.005 |
| case | leaf-acquisition.int32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:46.441850+00:00 | 1.998 |
| case | leaf-acquisition.int64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:48.440221+00:00 | 2.151 |
| case | leaf-acquisition.int64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:50.591702+00:00 | 2.197 |
| case | leaf-acquisition.float32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:52.788950+00:00 | 6.492 |
| case | leaf-acquisition.float32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:35:59.281248+00:00 | 6.543 |
| case | leaf-acquisition.float64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:05.824518+00:00 | 2.865 |
| case | leaf-acquisition.float64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:08.689444+00:00 | 2.827 |
| case | leaf-acquisition.decimal.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:11.516807+00:00 | 9.672 |
| case | leaf-acquisition.decimal.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:21.188826+00:00 | 9.698 |
| case | leaf-acquisition.bytes.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:30.886669+00:00 | 3.685 |
| case | leaf-acquisition.bytes.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:34.571724+00:00 | 3.615 |
| case | leaf-acquisition.date.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:38.186551+00:00 | 4.750 |
| case | leaf-acquisition.date.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:42.936892+00:00 | 4.859 |
| case | leaf-acquisition.time.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:47.796317+00:00 | 6.081 |
| case | leaf-acquisition.time.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:53.877465+00:00 | 6.121 |
| case | leaf-acquisition.timestamp.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:36:59.998379+00:00 | 14.695 |
| case | leaf-acquisition.timestamp.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:37:14.693001+00:00 | 14.659 |
| case | leaf-acquisition.uuid.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:37:29.352204+00:00 | 5.146 |
| case | leaf-acquisition.uuid.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-30T10:37:34.497816+00:00 | 5.124 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-09-30T10:37:39.621465+00:00 | 0.750 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-09-30T10:37:40.371169+00:00 | 4.105 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-09-30T10:37:44.475761+00:00 | 0.933 |
