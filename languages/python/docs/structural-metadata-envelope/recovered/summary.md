# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 596 | 67 | 23 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 6 | 9 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 1518 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3448.067 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-10-05T13:30:04.884969+00:00 | 3448.067 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-10-05T13:30:04.885080+00:00 | 3042.834 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:30:05.199365+00:00 | 1.924 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:30:07.123490+00:00 | 0.034 |
| setup | provisioner | member=snapshot-delivery | 2026-10-05T13:30:07.157408+00:00 | 3.856 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:30:11.027167+00:00 | 113.827 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-10-05T13:30:11.027181+00:00 | 3.562 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-10-05T13:30:30.469890+00:00 | 35.951 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:32:04.854010+00:00 | 122.368 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-10-05T13:32:04.854061+00:00 | 3.597 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-10-05T13:32:25.809004+00:00 | 34.568 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:34:07.222559+00:00 | 96.032 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-10-05T13:34:07.222599+00:00 | 0.712 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-10-05T13:34:26.463940+00:00 | 7.385 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:35:43.255230+00:00 | 66.416 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-10-05T13:35:43.255271+00:00 | 0.256 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-10-05T13:35:57.830992+00:00 | 1.180 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:36:49.670985+00:00 | 66.011 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-10-05T13:36:49.671022+00:00 | 0.278 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-10-05T13:37:04.207296+00:00 | 1.213 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:37:55.682069+00:00 | 9.884 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:38:05.566253+00:00 | 10.259 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:38:15.829143+00:00 | 182.595 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:41:18.424195+00:00 | 16.064 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-10-05T13:41:34.488372+00:00 | 147.629 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:44:02.119944+00:00 | 120.208 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-10-05T13:44:02.119973+00:00 | 3.411 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-10-05T13:44:22.055658+00:00 | 35.123 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:46:02.328702+00:00 | 128.276 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-10-05T13:46:02.328741+00:00 | 3.387 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-10-05T13:46:23.975458+00:00 | 34.509 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:48:10.605326+00:00 | 100.738 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-10-05T13:48:10.605366+00:00 | 0.839 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-10-05T13:48:30.755147+00:00 | 7.008 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:49:51.343522+00:00 | 74.249 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-10-05T13:49:51.343565+00:00 | 0.187 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-10-05T13:50:06.841030+00:00 | 1.367 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:51:05.592988+00:00 | 73.813 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-10-05T13:51:05.593038+00:00 | 0.225 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-10-05T13:51:20.923144+00:00 | 1.319 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:52:19.407674+00:00 | 8.048 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:52:27.456137+00:00 | 8.483 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:52:35.949692+00:00 | 165.146 |
| workload | leaf | member=snapshot-delivery, runtime=3.14 | 2026-10-05T13:55:21.096190+00:00 | 1363.500 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-10-05T14:18:04.600050+00:00 | 15.941 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-10-05T14:18:20.540722+00:00 | 146.555 |
| setup | close | member=snapshot-delivery | 2026-10-05T14:20:47.205930+00:00 | 0.259 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-10-05T14:20:47.771856+00:00 | 13.350 |
| member | instance-state | member=instance-state | 2026-10-05T14:21:01.128689+00:00 | 14.700 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-10-05T14:21:01.369358+00:00 | 0.117 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-10-05T14:21:01.486368+00:00 | 0.034 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-10-05T14:21:01.521001+00:00 | 0.885 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-10-05T14:21:02.405765+00:00 | 1.058 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-10-05T14:21:03.463786+00:00 | 1.672 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-10-05T14:21:05.135586+00:00 | 0.911 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-10-05T14:21:06.046814+00:00 | 0.864 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-10-05T14:21:06.911086+00:00 | 0.856 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-10-05T14:21:07.766890+00:00 | 0.772 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-10-05T14:21:08.538998+00:00 | 0.844 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-10-05T14:21:09.382936+00:00 | 1.083 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-10-05T14:21:10.466227+00:00 | 1.729 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-10-05T14:21:12.195537+00:00 | 0.952 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-10-05T14:21:13.147753+00:00 | 0.906 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-10-05T14:21:14.053782+00:00 | 0.885 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-10-05T14:21:14.939323+00:00 | 0.805 |
| member | write-lowering | member=write-lowering | 2026-10-05T14:21:15.845111+00:00 | 376.982 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-10-05T14:21:16.243717+00:00 | 0.083 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-10-05T14:21:16.326900+00:00 | 0.035 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:16.366277+00:00 | 0.831 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:17.196919+00:00 | 0.972 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:18.168543+00:00 | 0.828 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:18.996082+00:00 | 0.904 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:19.899689+00:00 | 1.098 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:20.998005+00:00 | 0.754 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:21.751896+00:00 | 0.942 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:22.693670+00:00 | 0.810 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:23.503413+00:00 | 0.868 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:24.371839+00:00 | 1.065 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:25.437379+00:00 | 0.746 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:26.183187+00:00 | 0.978 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:27.161507+00:00 | 0.822 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:27.983271+00:00 | 0.903 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:28.885953+00:00 | 1.088 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:29.974134+00:00 | 0.761 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:30.734830+00:00 | 0.938 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:31.673045+00:00 | 0.849 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:32.521812+00:00 | 0.898 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:33.420088+00:00 | 1.064 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:34.483833+00:00 | 0.745 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:35.228536+00:00 | 0.743 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:35.971107+00:00 | 0.782 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:36.752769+00:00 | 0.783 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:37.535629+00:00 | 0.832 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:38.367637+00:00 | 0.839 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:39.206524+00:00 | 0.718 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:39.924435+00:00 | 0.725 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:40.649083+00:00 | 0.813 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:41.461728+00:00 | 0.815 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:42.276953+00:00 | 1.073 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:43.350360+00:00 | 1.072 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:44.422307+00:00 | 0.841 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:45.263234+00:00 | 0.833 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:46.096572+00:00 | 1.220 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:47.316606+00:00 | 1.219 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:48.535877+00:00 | 0.813 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:49.348695+00:00 | 0.877 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:50.225894+00:00 | 0.980 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:51.205457+00:00 | 0.951 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:52.156660+00:00 | 1.046 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:53.202617+00:00 | 1.018 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:54.220188+00:00 | 1.410 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:55.629961+00:00 | 1.325 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:56.955306+00:00 | 1.024 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:57.979503+00:00 | 0.988 |
| case | plain.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:58.967058+00:00 | 0.842 |
| case | plain.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:21:59.808828+00:00 | 0.887 |
| case | plain.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:00.695484+00:00 | 0.851 |
| case | plain.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:01.546107+00:00 | 0.871 |
| case | plain.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:02.416969+00:00 | 0.895 |
| case | plain.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:03.311981+00:00 | 0.868 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:04.179815+00:00 | 0.964 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:05.144223+00:00 | 0.982 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:06.125902+00:00 | 0.972 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:07.097484+00:00 | 0.970 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:08.067803+00:00 | 0.991 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:09.058362+00:00 | 0.985 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:10.043271+00:00 | 1.111 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:11.153887+00:00 | 1.120 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:12.273995+00:00 | 1.131 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:13.405445+00:00 | 1.092 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:14.497343+00:00 | 1.116 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-10-05T14:22:15.613408+00:00 | 1.101 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-05T14:22:16.714166+00:00 | 1.076 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-05T14:22:17.790472+00:00 | 1.858 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-05T14:22:19.648694+00:00 | 4.950 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-05T14:22:24.598859+00:00 | 1.081 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-05T14:22:25.680188+00:00 | 1.880 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-10-05T14:22:27.559811+00:00 | 5.080 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-10-05T14:22:32.639368+00:00 | 0.787 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-05T14:22:33.425954+00:00 | 4.838 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-10-05T14:22:38.264268+00:00 | 0.981 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:39.249497+00:00 | 0.818 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:40.067079+00:00 | 1.032 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:41.099484+00:00 | 0.887 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:41.986052+00:00 | 0.959 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:42.944746+00:00 | 1.144 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:44.089094+00:00 | 0.811 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:44.900438+00:00 | 0.992 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:45.892838+00:00 | 0.875 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:46.767499+00:00 | 0.932 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:47.699060+00:00 | 1.141 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:48.840115+00:00 | 0.800 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:49.640479+00:00 | 1.013 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:50.653281+00:00 | 0.876 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:51.529208+00:00 | 0.959 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:52.487995+00:00 | 1.140 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:53.628212+00:00 | 0.804 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:54.432051+00:00 | 0.993 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:55.425509+00:00 | 0.864 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:56.289251+00:00 | 0.922 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:57.211261+00:00 | 1.090 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:58.301401+00:00 | 0.815 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:59.116079+00:00 | 0.795 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:22:59.911282+00:00 | 0.834 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:00.745790+00:00 | 0.841 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:01.587310+00:00 | 0.876 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:02.463845+00:00 | 0.878 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:03.342118+00:00 | 0.777 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:04.119494+00:00 | 0.778 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:04.897881+00:00 | 0.861 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:05.758903+00:00 | 0.858 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:06.616569+00:00 | 1.098 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:07.714401+00:00 | 1.097 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:08.811169+00:00 | 0.876 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:09.687296+00:00 | 0.876 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:10.563684+00:00 | 1.225 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:11.788629+00:00 | 1.224 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:13.013229+00:00 | 0.850 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:13.863111+00:00 | 0.849 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:14.712368+00:00 | 1.001 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:15.713738+00:00 | 0.990 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:16.704126+00:00 | 1.083 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:17.786945+00:00 | 1.060 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:18.847438+00:00 | 1.442 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:20.289892+00:00 | 1.347 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:21.636953+00:00 | 1.052 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:22.689091+00:00 | 1.034 |
| case | leaf.string.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:23.723107+00:00 | 1.452 |
| case | leaf.string.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:25.175035+00:00 | 1.448 |
| case | leaf.boolean.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:26.623385+00:00 | 1.056 |
| case | leaf.boolean.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:27.679935+00:00 | 1.165 |
| case | leaf.boolean.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:28.845059+00:00 | 1.061 |
| case | leaf.boolean.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:29.905758+00:00 | 1.151 |
| case | leaf.int32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:31.056652+00:00 | 1.156 |
| case | leaf.int32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:32.212553+00:00 | 1.350 |
| case | leaf.int32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:33.562352+00:00 | 1.219 |
| case | leaf.int32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:34.781892+00:00 | 1.344 |
| case | leaf.int64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:36.126192+00:00 | 1.139 |
| case | leaf.int64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:37.264957+00:00 | 1.379 |
| case | leaf.int64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:38.644333+00:00 | 1.149 |
| case | leaf.int64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:39.793133+00:00 | 1.362 |
| case | leaf.float32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:41.155655+00:00 | 1.665 |
| case | leaf.float32.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:42.820869+00:00 | 2.246 |
| case | leaf.float32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:45.066813+00:00 | 1.670 |
| case | leaf.float32.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:46.736822+00:00 | 2.251 |
| case | leaf.float64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:48.987544+00:00 | 1.235 |
| case | leaf.float64.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:50.222685+00:00 | 1.390 |
| case | leaf.float64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:51.613112+00:00 | 1.235 |
| case | leaf.float64.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:52.848438+00:00 | 1.379 |
| case | leaf.decimal.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:54.227039+00:00 | 2.021 |
| case | leaf.decimal.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:56.248408+00:00 | 3.512 |
| case | leaf.decimal.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:23:59.760261+00:00 | 2.015 |
| case | leaf.decimal.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:01.775738+00:00 | 3.526 |
| case | leaf.bytes.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:05.301324+00:00 | 1.264 |
| case | leaf.bytes.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:06.565690+00:00 | 1.547 |
| case | leaf.bytes.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:08.112707+00:00 | 1.253 |
| case | leaf.bytes.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:09.366148+00:00 | 1.532 |
| case | leaf.date.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:10.898143+00:00 | 1.376 |
| case | leaf.date.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:12.273788+00:00 | 1.841 |
| case | leaf.date.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:14.114630+00:00 | 1.457 |
| case | leaf.date.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:15.571929+00:00 | 1.813 |
| case | leaf.time.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:17.385356+00:00 | 1.395 |
| case | leaf.time.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:18.780377+00:00 | 1.962 |
| case | leaf.time.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:20.742724+00:00 | 1.396 |
| case | leaf.time.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:22.138911+00:00 | 1.920 |
| case | leaf.timestamp.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:24.059307+00:00 | 2.234 |
| case | leaf.timestamp.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:26.292963+00:00 | 3.633 |
| case | leaf.timestamp.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:29.925823+00:00 | 2.209 |
| case | leaf.timestamp.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:32.134512+00:00 | 3.612 |
| case | leaf.uuid.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:35.747054+00:00 | 1.937 |
| case | leaf.uuid.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:37.684167+00:00 | 2.595 |
| case | leaf.uuid.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:40.279017+00:00 | 1.943 |
| case | leaf.uuid.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:42.222266+00:00 | 2.630 |
| case | plain.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:44.852191+00:00 | 0.898 |
| case | plain.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:45.750047+00:00 | 0.899 |
| case | plain.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:46.649327+00:00 | 0.887 |
| case | plain.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:47.536135+00:00 | 0.911 |
| case | plain.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:48.447636+00:00 | 0.931 |
| case | plain.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:49.378846+00:00 | 0.912 |
| case | txtime.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:50.291095+00:00 | 0.995 |
| case | txtime.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:51.286440+00:00 | 1.007 |
| case | txtime.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:52.293216+00:00 | 0.999 |
| case | txtime.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:53.292566+00:00 | 1.002 |
| case | txtime.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:54.294570+00:00 | 1.019 |
| case | txtime.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:55.313239+00:00 | 1.005 |
| case | bitemporal.target-patch.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:56.318540+00:00 | 1.123 |
| case | bitemporal.target-replace.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:57.441980+00:00 | 1.134 |
| case | bitemporal.target-replace.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:58.576259+00:00 | 1.139 |
| case | bitemporal.target-patch.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:24:59.714830+00:00 | 1.109 |
| case | bitemporal.target-replace.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:25:00.823593+00:00 | 1.144 |
| case | bitemporal.target-replace.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-10-05T14:25:01.968040+00:00 | 1.131 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:03.098806+00:00 | 1.095 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:04.193702+00:00 | 1.808 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:06.002125+00:00 | 4.635 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:10.636890+00:00 | 1.110 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:11.747177+00:00 | 1.851 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:13.597811+00:00 | 4.730 |
| case | leaf-acquisition.string.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:18.327640+00:00 | 2.070 |
| case | leaf-acquisition.string.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:20.397364+00:00 | 2.084 |
| case | leaf-acquisition.boolean.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:22.481851+00:00 | 1.457 |
| case | leaf-acquisition.boolean.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:23.938803+00:00 | 1.461 |
| case | leaf-acquisition.int32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:25.399944+00:00 | 1.968 |
| case | leaf-acquisition.int32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:27.368236+00:00 | 1.977 |
| case | leaf-acquisition.int64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:29.345550+00:00 | 2.140 |
| case | leaf-acquisition.int64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:31.485470+00:00 | 2.151 |
| case | leaf-acquisition.float32.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:33.636473+00:00 | 6.708 |
| case | leaf-acquisition.float32.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:40.344862+00:00 | 6.548 |
| case | leaf-acquisition.float64.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:46.893076+00:00 | 2.924 |
| case | leaf-acquisition.float64.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:49.816764+00:00 | 2.903 |
| case | leaf-acquisition.decimal.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:25:52.719863+00:00 | 10.006 |
| case | leaf-acquisition.decimal.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:02.726065+00:00 | 9.931 |
| case | leaf-acquisition.bytes.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:12.656956+00:00 | 3.727 |
| case | leaf-acquisition.bytes.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:16.384150+00:00 | 3.792 |
| case | leaf-acquisition.date.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:20.176300+00:00 | 5.054 |
| case | leaf-acquisition.date.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:25.230646+00:00 | 4.892 |
| case | leaf-acquisition.time.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:30.122672+00:00 | 6.385 |
| case | leaf-acquisition.time.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:36.508212+00:00 | 6.239 |
| case | leaf-acquisition.timestamp.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:42.747595+00:00 | 16.294 |
| case | leaf-acquisition.timestamp.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:26:59.042097+00:00 | 16.599 |
| case | leaf-acquisition.uuid.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:27:15.641505+00:00 | 5.396 |
| case | leaf-acquisition.uuid.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-10-05T14:27:21.038051+00:00 | 5.529 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-10-05T14:27:26.566743+00:00 | 0.782 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-05T14:27:27.348853+00:00 | 4.349 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-10-05T14:27:31.697721+00:00 | 0.972 |
