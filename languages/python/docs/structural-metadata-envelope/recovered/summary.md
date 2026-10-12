# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 88 | 2 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 5 | 10 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1542 | 0 | 0 | 0 |
| feature-boundary | non-authoritative | 3.13, 3.14 | 180 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3562.946 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-10-11T23:19:51.938930+00:00 | 3562.946 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-10-11T23:19:51.939070+00:00 | 2969.840 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:19:52.251199+00:00 | 3.337 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:19:55.588506+00:00 | 0.028 |
| setup | provisioner | member=snapshot-delivery | 2026-10-11T23:19:55.617283+00:00 | 2.995 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:19:58.614727+00:00 | 120.457 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-10-11T23:19:58.614740+00:00 | 3.151 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-10-11T23:20:22.537599+00:00 | 33.948 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:21:59.072405+00:00 | 120.694 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-10-11T23:21:59.072450+00:00 | 3.110 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-10-11T23:22:19.573827+00:00 | 29.794 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:23:59.766904+00:00 | 97.307 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-10-11T23:23:59.766944+00:00 | 1.000 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-10-11T23:24:20.876491+00:00 | 6.187 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:25:37.074448+00:00 | 68.608 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-10-11T23:25:37.074486+00:00 | 0.155 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-10-11T23:25:51.642692+00:00 | 1.065 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:26:45.683150+00:00 | 68.245 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-10-11T23:26:45.683195+00:00 | 0.225 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-10-11T23:27:00.814053+00:00 | 1.093 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:27:53.928310+00:00 | 9.767 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:28:03.695136+00:00 | 10.178 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:28:13.873391+00:00 | 187.828 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:31:21.702277+00:00 | 16.544 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-10-11T23:31:38.246411+00:00 | 148.202 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:34:06.450783+00:00 | 115.303 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-10-11T23:34:06.450808+00:00 | 3.152 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-10-11T23:34:25.299432+00:00 | 29.512 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:36:01.753847+00:00 | 121.936 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-10-11T23:36:01.753890+00:00 | 3.049 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-10-11T23:36:21.693060+00:00 | 29.543 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:38:03.689978+00:00 | 98.750 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-10-11T23:38:03.690017+00:00 | 0.919 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-10-11T23:38:22.612949+00:00 | 5.714 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:39:42.440323+00:00 | 80.284 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-10-11T23:39:42.440359+00:00 | 0.154 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-10-11T23:40:01.494603+00:00 | 1.144 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:41:02.724833+00:00 | 75.900 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-10-11T23:41:02.724876+00:00 | 0.224 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-10-11T23:41:17.772076+00:00 | 1.048 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:42:18.625237+00:00 | 7.480 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:42:26.105387+00:00 | 7.905 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:42:34.010993+00:00 | 160.620 |
| workload | leaf | member=snapshot-delivery, runtime=3.14 | 2026-10-11T23:45:14.631406+00:00 | 1291.058 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-10-12T00:06:45.691084+00:00 | 16.236 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-10-12T00:07:01.927646+00:00 | 139.397 |
| setup | close | member=snapshot-delivery | 2026-10-12T00:09:21.390664+00:00 | 0.189 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-10-12T00:09:21.816627+00:00 | 12.388 |
| member | instance-state | member=instance-state | 2026-10-12T00:09:34.208067+00:00 | 14.449 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-10-12T00:09:34.440783+00:00 | 0.125 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-10-12T00:09:34.566187+00:00 | 0.028 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-10-12T00:09:34.594127+00:00 | 0.951 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-10-12T00:09:35.544703+00:00 | 1.098 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-10-12T00:09:36.642817+00:00 | 1.716 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-10-12T00:09:38.358954+00:00 | 0.954 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-10-12T00:09:39.313091+00:00 | 0.898 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-10-12T00:09:40.211028+00:00 | 0.888 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-10-12T00:09:41.099279+00:00 | 0.793 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-10-12T00:09:41.891837+00:00 | 0.796 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-10-12T00:09:42.687607+00:00 | 0.991 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-10-12T00:09:43.678517+00:00 | 1.590 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-10-12T00:09:45.268829+00:00 | 0.881 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-10-12T00:09:46.149405+00:00 | 0.832 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-10-12T00:09:46.981725+00:00 | 0.828 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-10-12T00:09:47.810125+00:00 | 0.760 |
| member | write-lowering | member=write-lowering | 2026-10-12T00:09:48.668345+00:00 | 544.997 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-10-12T00:09:49.050585+00:00 | 0.076 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-10-12T00:09:49.127010+00:00 | 0.028 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:49.155191+00:00 | 0.957 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:50.112687+00:00 | 1.025 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:51.137600+00:00 | 0.880 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:52.017599+00:00 | 0.958 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:52.975544+00:00 | 1.138 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:54.113308+00:00 | 0.790 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:54.903084+00:00 | 0.993 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:55.895635+00:00 | 0.858 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:56.753792+00:00 | 0.912 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:57.665572+00:00 | 1.100 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:58.765619+00:00 | 0.790 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:09:59.555701+00:00 | 1.021 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:00.576445+00:00 | 0.850 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:01.426965+00:00 | 0.969 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:02.396339+00:00 | 1.116 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:03.511874+00:00 | 0.800 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:04.312099+00:00 | 0.991 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:05.302741+00:00 | 0.855 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:06.157433+00:00 | 0.917 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:07.074694+00:00 | 1.096 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:08.170265+00:00 | 0.794 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:08.964428+00:00 | 0.791 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:09.755605+00:00 | 0.832 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:10.587154+00:00 | 0.829 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:11.416685+00:00 | 0.892 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:12.308400+00:00 | 0.875 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:13.183750+00:00 | 0.779 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:13.962776+00:00 | 0.764 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:14.726627+00:00 | 0.862 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:15.588675+00:00 | 0.857 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:16.445624+00:00 | 1.137 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:17.582479+00:00 | 1.133 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:18.715191+00:00 | 0.883 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:19.598726+00:00 | 0.885 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:20.483522+00:00 | 1.273 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:21.756140+00:00 | 1.287 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:23.043429+00:00 | 0.858 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:23.901624+00:00 | 0.870 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:24.771510+00:00 | 1.002 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:25.773180+00:00 | 0.997 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:26.770057+00:00 | 1.092 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:27.861875+00:00 | 1.066 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:28.927904+00:00 | 1.460 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:30.388438+00:00 | 1.363 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:31.751808+00:00 | 1.069 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:32.820576+00:00 | 1.026 |
| case | plain.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:33.846704+00:00 | 0.886 |
| case | plain.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:34.732938+00:00 | 0.903 |
| case | plain.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:35.636247+00:00 | 0.911 |
| case | plain.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:36.547011+00:00 | 0.919 |
| case | plain.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:37.465805+00:00 | 0.970 |
| case | plain.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:38.435916+00:00 | 0.914 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:39.350185+00:00 | 1.026 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:40.376646+00:00 | 1.031 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:41.407445+00:00 | 1.029 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:42.436856+00:00 | 1.013 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:43.449997+00:00 | 1.046 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:44.495623+00:00 | 1.015 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:45.510808+00:00 | 1.128 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:46.638566+00:00 | 1.133 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:47.771327+00:00 | 1.126 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:48.897362+00:00 | 1.117 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:50.014128+00:00 | 1.134 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-12T00:10:51.148536+00:00 | 1.118 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-12T00:10:52.266478+00:00 | 1.081 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-12T00:10:53.347338+00:00 | 1.683 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-12T00:10:55.030692+00:00 | 4.071 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-12T00:10:59.102197+00:00 | 1.075 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-12T00:11:00.176881+00:00 | 1.691 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-12T00:11:01.868337+00:00 | 4.180 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-10-12T00:11:06.048684+00:00 | 0.806 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-12T00:11:06.854678+00:00 | 4.898 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-12T00:11:11.752631+00:00 | 1.013 |
| case | predicate-flush.reaching.objects-128.columns | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-12T00:11:12.765461+00:00 | 35.716 |
| case | predicate-flush.reaching.objects-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-12T00:11:48.481693+00:00 | 34.891 |
| case | predicate-flush.unchanged.objects-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-12T00:12:23.373120+00:00 | 17.165 |
| case | predicate-flush.wide.history-128.document | member=write-lowering, runtime=3.13, window=predicate-flush | 2026-10-12T00:12:40.537998+00:00 | 11.958 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:52.495764+00:00 | 0.794 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:53.289478+00:00 | 1.005 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:54.294724+00:00 | 0.846 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:55.140778+00:00 | 0.926 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:56.066829+00:00 | 1.080 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:57.147121+00:00 | 0.797 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:57.944147+00:00 | 0.964 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:58.908615+00:00 | 0.832 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:12:59.740983+00:00 | 0.899 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:00.639599+00:00 | 1.053 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:01.692470+00:00 | 0.789 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:02.481360+00:00 | 0.984 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:03.465042+00:00 | 0.842 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:04.306987+00:00 | 0.920 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:05.226718+00:00 | 1.088 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:06.314804+00:00 | 0.817 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:07.132134+00:00 | 0.968 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:08.099996+00:00 | 0.852 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:08.952125+00:00 | 0.901 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:09.853025+00:00 | 1.051 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:10.904156+00:00 | 0.791 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:11.694830+00:00 | 0.790 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:12.484853+00:00 | 0.818 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:13.303317+00:00 | 0.834 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:14.137009+00:00 | 0.869 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:15.005664+00:00 | 0.878 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:15.883631+00:00 | 0.775 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:16.659058+00:00 | 0.768 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:17.427235+00:00 | 0.853 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:18.280636+00:00 | 0.852 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:19.133035+00:00 | 1.074 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:20.207064+00:00 | 1.080 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:21.287505+00:00 | 0.882 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:22.169923+00:00 | 0.859 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:23.029240+00:00 | 1.195 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:24.223872+00:00 | 1.186 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:25.410208+00:00 | 0.842 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:26.252304+00:00 | 0.831 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:27.083796+00:00 | 0.977 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:28.060344+00:00 | 0.965 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:29.025002+00:00 | 1.038 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:30.063491+00:00 | 1.015 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:31.078372+00:00 | 1.366 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:32.444456+00:00 | 1.276 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:33.720360+00:00 | 1.018 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:34.737967+00:00 | 0.986 |
| case | leaf.string.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:35.724433+00:00 | 1.385 |
| case | leaf.string.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:37.109205+00:00 | 1.389 |
| case | leaf.boolean.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:38.498092+00:00 | 1.048 |
| case | leaf.boolean.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:39.546142+00:00 | 1.142 |
| case | leaf.boolean.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:40.687734+00:00 | 1.033 |
| case | leaf.boolean.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:41.720373+00:00 | 1.113 |
| case | leaf.int32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:42.833492+00:00 | 1.100 |
| case | leaf.int32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:43.933234+00:00 | 1.303 |
| case | leaf.int32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:45.235901+00:00 | 1.094 |
| case | leaf.int32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:46.329553+00:00 | 1.301 |
| case | leaf.int64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:47.630673+00:00 | 1.108 |
| case | leaf.int64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:48.738903+00:00 | 1.330 |
| case | leaf.int64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:50.068504+00:00 | 1.113 |
| case | leaf.int64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:51.181267+00:00 | 1.330 |
| case | leaf.float32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:52.511649+00:00 | 1.624 |
| case | leaf.float32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:54.136183+00:00 | 2.161 |
| case | leaf.float32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:56.297251+00:00 | 1.625 |
| case | leaf.float32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:13:57.922336+00:00 | 2.136 |
| case | leaf.float64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:00.058651+00:00 | 1.186 |
| case | leaf.float64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:01.244622+00:00 | 1.310 |
| case | leaf.float64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:02.554377+00:00 | 1.196 |
| case | leaf.float64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:03.750072+00:00 | 1.324 |
| case | leaf.decimal.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:05.074229+00:00 | 1.946 |
| case | leaf.decimal.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:07.020607+00:00 | 3.384 |
| case | leaf.decimal.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:10.404915+00:00 | 1.980 |
| case | leaf.decimal.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:12.385312+00:00 | 3.370 |
| case | leaf.bytes.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:15.755480+00:00 | 1.201 |
| case | leaf.bytes.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:16.956529+00:00 | 1.469 |
| case | leaf.bytes.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:18.425881+00:00 | 1.191 |
| case | leaf.bytes.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:19.617308+00:00 | 1.432 |
| case | leaf.date.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:21.049843+00:00 | 1.304 |
| case | leaf.date.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:22.354342+00:00 | 1.706 |
| case | leaf.date.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:24.060435+00:00 | 1.306 |
| case | leaf.date.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:25.366291+00:00 | 1.734 |
| case | leaf.time.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:27.100817+00:00 | 1.348 |
| case | leaf.time.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:28.449224+00:00 | 1.736 |
| case | leaf.time.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:30.185317+00:00 | 1.341 |
| case | leaf.time.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:31.526551+00:00 | 1.740 |
| case | leaf.timestamp.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:33.266754+00:00 | 2.064 |
| case | leaf.timestamp.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:35.330553+00:00 | 3.292 |
| case | leaf.timestamp.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:38.622680+00:00 | 2.077 |
| case | leaf.timestamp.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:40.700194+00:00 | 3.347 |
| case | leaf.uuid.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:44.047312+00:00 | 1.851 |
| case | leaf.uuid.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:45.897941+00:00 | 2.406 |
| case | leaf.uuid.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:48.303552+00:00 | 1.851 |
| case | leaf.uuid.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:50.154271+00:00 | 2.450 |
| case | plain.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:52.604644+00:00 | 0.863 |
| case | plain.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:53.467425+00:00 | 0.907 |
| case | plain.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:54.374959+00:00 | 0.871 |
| case | plain.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:55.245623+00:00 | 0.893 |
| case | plain.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:56.139101+00:00 | 0.903 |
| case | plain.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:57.041792+00:00 | 0.898 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:57.940255+00:00 | 0.978 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:58.918679+00:00 | 0.991 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:14:59.909889+00:00 | 0.980 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:00.889772+00:00 | 0.980 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:01.869886+00:00 | 0.989 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:02.858662+00:00 | 0.991 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:03.849440+00:00 | 1.068 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:04.917920+00:00 | 1.090 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:06.007624+00:00 | 1.104 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:07.111497+00:00 | 1.069 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:08.180456+00:00 | 1.068 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-12T00:15:09.248666+00:00 | 1.067 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:10.316107+00:00 | 1.017 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:11.333480+00:00 | 1.540 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:12.873860+00:00 | 3.472 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:16.346081+00:00 | 1.013 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:17.359439+00:00 | 1.528 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:18.887949+00:00 | 3.624 |
| case | leaf-acquisition.string.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:22.512267+00:00 | 2.023 |
| case | leaf-acquisition.string.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:24.535340+00:00 | 1.971 |
| case | leaf-acquisition.boolean.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:26.506284+00:00 | 1.354 |
| case | leaf-acquisition.boolean.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:27.860351+00:00 | 1.352 |
| case | leaf-acquisition.int32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:29.212441+00:00 | 1.857 |
| case | leaf-acquisition.int32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:31.069007+00:00 | 1.848 |
| case | leaf-acquisition.int64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:32.916691+00:00 | 2.009 |
| case | leaf-acquisition.int64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:34.925657+00:00 | 2.041 |
| case | leaf-acquisition.float32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:36.967008+00:00 | 6.362 |
| case | leaf-acquisition.float32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:43.328678+00:00 | 6.392 |
| case | leaf-acquisition.float64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:49.720285+00:00 | 2.727 |
| case | leaf-acquisition.float64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:52.447166+00:00 | 2.745 |
| case | leaf-acquisition.decimal.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:15:55.192323+00:00 | 9.285 |
| case | leaf-acquisition.decimal.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:04.477871+00:00 | 9.389 |
| case | leaf-acquisition.bytes.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:13.866735+00:00 | 3.531 |
| case | leaf-acquisition.bytes.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:17.398057+00:00 | 3.444 |
| case | leaf-acquisition.date.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:20.841971+00:00 | 4.735 |
| case | leaf-acquisition.date.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:25.577319+00:00 | 4.690 |
| case | leaf-acquisition.time.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:30.267351+00:00 | 5.830 |
| case | leaf-acquisition.time.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:36.096951+00:00 | 5.909 |
| case | leaf-acquisition.timestamp.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:42.005899+00:00 | 14.299 |
| case | leaf-acquisition.timestamp.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:16:56.305050+00:00 | 14.687 |
| case | leaf-acquisition.uuid.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:17:10.992208+00:00 | 5.055 |
| case | leaf-acquisition.uuid.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-12T00:17:16.047748+00:00 | 4.950 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-10-12T00:17:20.997470+00:00 | 0.784 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-12T00:17:21.781544+00:00 | 4.044 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-12T00:17:25.825802+00:00 | 0.956 |
| case | predicate-flush.reaching.objects-128.columns | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-12T00:17:26.781771+00:00 | 31.179 |
| case | predicate-flush.reaching.objects-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-12T00:17:57.960911+00:00 | 31.138 |
| case | predicate-flush.unchanged.objects-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-12T00:18:29.099239+00:00 | 14.123 |
| case | predicate-flush.wide.history-128.document | member=write-lowering, runtime=3.14, window=predicate-flush | 2026-10-12T00:18:43.222012+00:00 | 10.299 |
| member | feature-boundary | member=feature-boundary | 2026-10-12T00:18:53.710011+00:00 | 21.172 |
| setup | identity | member=feature-boundary, runtime=3.13 | 2026-10-12T00:18:53.925328+00:00 | 0.076 |
| setup | identity | member=feature-boundary, runtime=3.14 | 2026-10-12T00:18:54.001443+00:00 | 0.028 |
| case | predicate.shallow-scalar.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-12T00:18:54.029528+00:00 | 0.325 |
| case | predicate.shallow-scalar.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-12T00:18:54.354320+00:00 | 0.395 |
| case | predicate.scalar-any.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-12T00:18:54.749658+00:00 | 0.302 |
| case | predicate.scalar-any.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-12T00:18:55.051337+00:00 | 0.402 |
| case | predicate.nested-all.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-12T00:18:55.453633+00:00 | 0.307 |
| case | predicate.nested-all.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-12T00:18:55.760759+00:00 | 0.420 |
| case | predicate.two-hop-to-one.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-12T00:18:56.180904+00:00 | 0.309 |
| case | predicate.two-hop-to-one.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-12T00:18:56.490324+00:00 | 0.428 |
| case | predicate.quantifier-through-to-one.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-12T00:18:56.917951+00:00 | 0.304 |
| case | predicate.quantifier-through-to-one.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-12T00:18:57.221552+00:00 | 0.419 |
| case | predicate.subtype-narrowing.binding | member=feature-boundary, runtime=3.13, window=typed-predicate-binding | 2026-10-12T00:18:57.640682+00:00 | 0.310 |
| case | predicate.subtype-narrowing.cold-plan | member=feature-boundary, runtime=3.13, window=typed-cold-plan | 2026-10-12T00:18:57.951117+00:00 | 0.423 |
| case | scalar-collection.integer.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:18:58.374616+00:00 | 0.289 |
| case | scalar-collection.integer.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:18:58.663228+00:00 | 0.289 |
| case | scalar-collection.integer.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:18:58.951844+00:00 | 0.292 |
| case | scalar-collection.integer.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:18:59.243782+00:00 | 0.289 |
| case | scalar-collection.integer.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:18:59.532603+00:00 | 0.328 |
| case | scalar-collection.integer.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:18:59.860537+00:00 | 0.321 |
| case | scalar-collection.string.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:19:00.181141+00:00 | 0.287 |
| case | scalar-collection.string.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:19:00.468043+00:00 | 0.287 |
| case | scalar-collection.string.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:19:00.755161+00:00 | 0.292 |
| case | scalar-collection.string.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:19:01.047426+00:00 | 0.289 |
| case | scalar-collection.string.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:19:01.336137+00:00 | 0.367 |
| case | scalar-collection.string.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:19:01.703536+00:00 | 0.301 |
| case | scalar-collection.decimal.size-0.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:19:02.004262+00:00 | 0.291 |
| case | scalar-collection.decimal.size-0.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:19:02.295500+00:00 | 0.289 |
| case | scalar-collection.decimal.size-8.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:19:02.584647+00:00 | 0.313 |
| case | scalar-collection.decimal.size-8.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:19:02.898152+00:00 | 0.317 |
| case | scalar-collection.decimal.size-128.encode | member=feature-boundary, runtime=3.13, window=scalar-collection-encode | 2026-10-12T00:19:03.214810+00:00 | 0.679 |
| case | scalar-collection.decimal.size-128.decode | member=feature-boundary, runtime=3.13, window=scalar-collection-decode | 2026-10-12T00:19:03.893488+00:00 | 0.725 |
| case | predicate.shallow-scalar.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-12T00:19:04.618572+00:00 | 0.289 |
| case | predicate.shallow-scalar.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-12T00:19:04.907868+00:00 | 0.378 |
| case | predicate.scalar-any.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-12T00:19:05.285912+00:00 | 0.309 |
| case | predicate.scalar-any.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-12T00:19:05.595275+00:00 | 0.385 |
| case | predicate.nested-all.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-12T00:19:05.980615+00:00 | 0.293 |
| case | predicate.nested-all.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-12T00:19:06.273472+00:00 | 0.408 |
| case | predicate.two-hop-to-one.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-12T00:19:06.681417+00:00 | 0.300 |
| case | predicate.two-hop-to-one.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-12T00:19:06.981234+00:00 | 0.410 |
| case | predicate.quantifier-through-to-one.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-12T00:19:07.390813+00:00 | 0.324 |
| case | predicate.quantifier-through-to-one.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-12T00:19:07.714632+00:00 | 0.437 |
| case | predicate.subtype-narrowing.binding | member=feature-boundary, runtime=3.14, window=typed-predicate-binding | 2026-10-12T00:19:08.151761+00:00 | 0.317 |
| case | predicate.subtype-narrowing.cold-plan | member=feature-boundary, runtime=3.14, window=typed-cold-plan | 2026-10-12T00:19:08.468843+00:00 | 0.396 |
| case | scalar-collection.integer.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:08.864389+00:00 | 0.282 |
| case | scalar-collection.integer.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:09.146311+00:00 | 0.283 |
| case | scalar-collection.integer.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:09.429152+00:00 | 0.281 |
| case | scalar-collection.integer.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:09.710506+00:00 | 0.290 |
| case | scalar-collection.integer.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:10.000973+00:00 | 0.316 |
| case | scalar-collection.integer.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:10.316693+00:00 | 0.327 |
| case | scalar-collection.string.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:10.643907+00:00 | 0.279 |
| case | scalar-collection.string.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:10.923160+00:00 | 0.280 |
| case | scalar-collection.string.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:11.203605+00:00 | 0.285 |
| case | scalar-collection.string.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:11.488373+00:00 | 0.283 |
| case | scalar-collection.string.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:11.771437+00:00 | 0.353 |
| case | scalar-collection.string.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:12.124685+00:00 | 0.285 |
| case | scalar-collection.decimal.size-0.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:12.409831+00:00 | 0.281 |
| case | scalar-collection.decimal.size-0.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:12.691041+00:00 | 0.280 |
| case | scalar-collection.decimal.size-8.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:12.971546+00:00 | 0.301 |
| case | scalar-collection.decimal.size-8.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:13.272990+00:00 | 0.309 |
| case | scalar-collection.decimal.size-128.encode | member=feature-boundary, runtime=3.14, window=scalar-collection-encode | 2026-10-12T00:19:13.581644+00:00 | 0.607 |
| case | scalar-collection.decimal.size-128.decode | member=feature-boundary, runtime=3.14, window=scalar-collection-decode | 2026-10-12T00:19:14.189100+00:00 | 0.617 |
