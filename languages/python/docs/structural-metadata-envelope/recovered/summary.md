# Python cost report

| Subject | Authority | Runtimes | Readings | Within | Outside | Unavailable |
|---|---|---|---:|---:|---:|---:|
| snapshot-delivery | authoritative | 3.13, 3.14 | 530 | 73 | 17 | 0 |
| lifecycle-overhead | non-authoritative | - | 87 | 4 | 11 | 0 |
| instance-state | non-authoritative | - | 696 | 4 | 4 | 0 |
| write-lowering | non-authoritative | 3.13, 3.14 | 974 | 0 | 0 | 0 |

Budget outcomes are advisory. This collector fails only for a missing or invalid required envelope.

## Durations

Critical path: 3898.533 s, the `python-report-cost` collection span. Nested spans are included in their parents and are never summed.

| Scope | Name | Labels | Started | Seconds |
|---|---|---|---|---:|
| collection | python-report-cost | - | 2026-09-23T19:29:51.765437+00:00 | 3898.533 |
| member | snapshot-delivery | member=snapshot-delivery | 2026-09-23T19:29:51.765548+00:00 | 3727.061 |
| setup | identity | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:29:52.035596+00:00 | 0.167 |
| setup | identity | member=snapshot-delivery, runtime=3.14 | 2026-09-23T19:29:52.203073+00:00 | 0.033 |
| setup | provisioner | member=snapshot-delivery | 2026-09-23T19:29:52.236475+00:00 | 6.384 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:29:58.627164+00:00 | 279.067 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=conventional-fanout | 2026-09-23T19:29:58.627175+00:00 | 8.639 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=conventional-fanout | 2026-09-23T19:30:38.978079+00:00 | 37.302 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:34:37.694941+00:00 | 294.333 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=duplicate-include | 2026-09-23T19:34:37.694995+00:00 | 11.671 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=duplicate-include | 2026-09-23T19:35:22.200595+00:00 | 37.135 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:39:32.028250+00:00 | 271.242 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=document-heavy | 2026-09-23T19:39:32.028290+00:00 | 5.252 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=document-heavy | 2026-09-23T19:40:11.160436+00:00 | 12.559 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:44:03.271350+00:00 | 230.214 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=versioned-document | 2026-09-23T19:44:03.271393+00:00 | 0.725 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=versioned-document | 2026-09-23T19:44:33.846476+00:00 | 6.696 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:47:53.486184+00:00 | 235.919 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.13, workload=bitemporal-current | 2026-09-23T19:47:53.486226+00:00 | 0.736 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.13, workload=bitemporal-current | 2026-09-23T19:48:24.690111+00:00 | 7.413 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:51:49.405896+00:00 | 12.113 |
| workload | stress-document | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:52:01.518666+00:00 | 12.359 |
| workload | geometry | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:52:13.877979+00:00 | 217.469 |
| workload | plan | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:55:51.347675+00:00 | 18.216 |
| workload | control | member=snapshot-delivery, runtime=3.13 | 2026-09-23T19:56:09.563811+00:00 | 182.044 |
| workload | conventional-fanout | member=snapshot-delivery, runtime=3.14 | 2026-09-23T19:59:11.609911+00:00 | 366.382 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=conventional-fanout | 2026-09-23T19:59:11.609933+00:00 | 11.916 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=conventional-fanout | 2026-09-23T19:59:58.023031+00:00 | 45.072 |
| workload | duplicate-include | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:05:17.993079+00:00 | 349.015 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=duplicate-include | 2026-09-23T20:05:17.993130+00:00 | 13.470 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=duplicate-include | 2026-09-23T20:06:08.052752+00:00 | 38.475 |
| workload | document-heavy | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:11:07.020360+00:00 | 311.481 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=document-heavy | 2026-09-23T20:11:07.020401+00:00 | 4.621 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=document-heavy | 2026-09-23T20:11:50.858833+00:00 | 11.460 |
| workload | versioned-document | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:16:18.502697+00:00 | 266.516 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=versioned-document | 2026-09-23T20:16:18.502738+00:00 | 0.557 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=versioned-document | 2026-09-23T20:16:52.391244+00:00 | 7.151 |
| workload | bitemporal-current | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:20:45.020243+00:00 | 270.988 |
| setup | provision | member=snapshot-delivery, roots=200, runtime=3.14, workload=bitemporal-current | 2026-09-23T20:20:45.020280+00:00 | 0.452 |
| setup | provision | member=snapshot-delivery, roots=2000, runtime=3.14, workload=bitemporal-current | 2026-09-23T20:21:19.095420+00:00 | 5.252 |
| workload | stress-columns | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:25:16.010021+00:00 | 10.194 |
| workload | stress-document | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:25:26.204214+00:00 | 10.891 |
| workload | geometry | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:25:37.095200+00:00 | 181.419 |
| workload | plan | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:28:38.515437+00:00 | 17.983 |
| workload | control | member=snapshot-delivery, runtime=3.14 | 2026-09-23T20:28:56.498189+00:00 | 181.266 |
| setup | close | member=snapshot-delivery | 2026-09-23T20:31:57.845804+00:00 | 0.626 |
| member | lifecycle-overhead | member=lifecycle-overhead | 2026-09-23T20:31:58.884315+00:00 | 14.503 |
| member | instance-state | member=instance-state | 2026-09-23T20:32:13.394396+00:00 | 19.095 |
| setup | identity | member=instance-state, runtime=3.13 | 2026-09-23T20:32:13.633579+00:00 | 0.208 |
| setup | identity | member=instance-state, runtime=3.14 | 2026-09-23T20:32:13.843646+00:00 | 0.034 |
| scenario | shallow | member=instance-state, runtime=3.13 | 2026-09-23T20:32:13.877966+00:00 | 1.103 |
| scenario | wide | member=instance-state, runtime=3.13 | 2026-09-23T20:32:14.980597+00:00 | 1.338 |
| scenario | nested | member=instance-state, runtime=3.13 | 2026-09-23T20:32:16.319143+00:00 | 2.247 |
| scenario | nullable | member=instance-state, runtime=3.13 | 2026-09-23T20:32:18.566634+00:00 | 1.133 |
| scenario | partial | member=instance-state, runtime=3.13 | 2026-09-23T20:32:19.699664+00:00 | 1.065 |
| scenario | polymorphic | member=instance-state, runtime=3.13 | 2026-09-23T20:32:20.764728+00:00 | 1.254 |
| scenario | warmed | member=instance-state, runtime=3.13 | 2026-09-23T20:32:22.018947+00:00 | 0.947 |
| scenario | shallow | member=instance-state, runtime=3.14 | 2026-09-23T20:32:22.966344+00:00 | 1.049 |
| scenario | wide | member=instance-state, runtime=3.14 | 2026-09-23T20:32:24.015572+00:00 | 1.362 |
| scenario | nested | member=instance-state, runtime=3.14 | 2026-09-23T20:32:25.377688+00:00 | 2.366 |
| scenario | nullable | member=instance-state, runtime=3.14 | 2026-09-23T20:32:27.743814+00:00 | 1.204 |
| scenario | partial | member=instance-state, runtime=3.14 | 2026-09-23T20:32:28.947541+00:00 | 1.180 |
| scenario | polymorphic | member=instance-state, runtime=3.14 | 2026-09-23T20:32:30.127645+00:00 | 1.291 |
| scenario | warmed | member=instance-state, runtime=3.14 | 2026-09-23T20:32:31.418390+00:00 | 0.980 |
| member | write-lowering | member=write-lowering | 2026-09-23T20:32:32.507084+00:00 | 137.780 |
| setup | identity | member=write-lowering, runtime=3.13 | 2026-09-23T20:32:32.814923+00:00 | 0.106 |
| setup | identity | member=write-lowering, runtime=3.14 | 2026-09-23T20:32:32.921477+00:00 | 0.035 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:32.956500+00:00 | 0.745 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:33.701074+00:00 | 0.625 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:34.326478+00:00 | 0.626 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:34.952434+00:00 | 0.616 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:35.568733+00:00 | 0.643 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:36.211536+00:00 | 0.604 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:36.815302+00:00 | 0.613 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:37.428319+00:00 | 0.610 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:38.038412+00:00 | 0.601 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:38.639660+00:00 | 0.629 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:39.269091+00:00 | 0.616 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:39.884866+00:00 | 0.637 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:40.522307+00:00 | 0.625 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:41.147303+00:00 | 0.616 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:41.763767+00:00 | 0.641 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:42.404811+00:00 | 0.602 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:43.006813+00:00 | 0.614 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:43.620838+00:00 | 0.617 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:44.237435+00:00 | 0.642 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:44.879381+00:00 | 0.650 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:45.529860+00:00 | 0.612 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:46.141558+00:00 | 0.615 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:46.756240+00:00 | 0.645 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:47.400913+00:00 | 0.665 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:48.065804+00:00 | 0.681 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:48.746390+00:00 | 0.680 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:49.426399+00:00 | 0.600 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:50.026056+00:00 | 0.603 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:50.628897+00:00 | 0.661 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:51.289741+00:00 | 0.659 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:51.948416+00:00 | 0.866 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:52.814253+00:00 | 0.894 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:53.708489+00:00 | 0.721 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:54.429654+00:00 | 0.721 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:55.150821+00:00 | 0.996 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:56.146964+00:00 | 0.973 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:57.120246+00:00 | 0.677 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:57.796798+00:00 | 0.665 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:58.462060+00:00 | 0.698 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:59.160407+00:00 | 0.664 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:32:59.824911+00:00 | 0.699 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:33:00.524283+00:00 | 0.690 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:33:01.214736+00:00 | 0.962 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:33:02.177102+00:00 | 1.013 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:33:03.190038+00:00 | 0.751 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.13, window=keyed-write | 2026-09-23T20:33:03.940832+00:00 | 0.716 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-23T20:33:04.656968+00:00 | 1.340 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-23T20:33:05.996842+00:00 | 3.220 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-23T20:33:09.216650+00:00 | 11.907 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-23T20:33:21.123974+00:00 | 1.356 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-23T20:33:22.480415+00:00 | 3.358 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.13, window=predicate-acquisition | 2026-09-23T20:33:25.838307+00:00 | 11.799 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.13, window=wire-insert-response | 2026-09-23T20:33:37.637663+00:00 | 0.577 |
| case | model.prepared | member=write-lowering, runtime=3.13, window=model-preparation | 2026-09-23T20:33:38.215131+00:00 | 4.646 |
| case | model.prepared.family | member=write-lowering, runtime=3.13, window=model-preparation | 2026-09-23T20:33:42.861008+00:00 | 0.830 |
| case | txtime.opening.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:43.691159+00:00 | 0.643 |
| case | txtime.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:44.333874+00:00 | 0.643 |
| case | txtime.unchanged.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:44.977039+00:00 | 0.642 |
| case | plain.changed.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:45.618619+00:00 | 0.632 |
| case | bitemporal.interior.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:46.250274+00:00 | 0.658 |
| case | txtime.opening.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:46.908127+00:00 | 0.631 |
| case | txtime.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:47.539072+00:00 | 0.642 |
| case | txtime.unchanged.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:48.181523+00:00 | 0.638 |
| case | plain.changed.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:48.819126+00:00 | 0.619 |
| case | bitemporal.interior.columns.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:49.438535+00:00 | 0.647 |
| case | txtime.opening.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:50.085841+00:00 | 0.645 |
| case | txtime.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:50.730907+00:00 | 0.650 |
| case | txtime.unchanged.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:51.380507+00:00 | 0.646 |
| case | plain.changed.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:52.026843+00:00 | 0.634 |
| case | bitemporal.interior.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:52.661201+00:00 | 0.658 |
| case | txtime.opening.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:53.319623+00:00 | 0.615 |
| case | txtime.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:53.935055+00:00 | 0.623 |
| case | txtime.unchanged.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:54.557723+00:00 | 0.632 |
| case | plain.changed.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:55.189695+00:00 | 0.615 |
| case | bitemporal.interior.document.wire | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:55.805066+00:00 | 0.641 |
| case | geometry.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:56.446198+00:00 | 0.632 |
| case | geometry.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:57.078075+00:00 | 0.635 |
| case | geometry.depth-4.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:57.713206+00:00 | 0.660 |
| case | geometry.depth-4.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:58.372832+00:00 | 0.739 |
| case | geometry.depth-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:59.112285+00:00 | 0.724 |
| case | geometry.depth-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:33:59.835843+00:00 | 0.698 |
| case | geometry.many-0.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:00.534107+00:00 | 0.628 |
| case | geometry.many-0.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:01.162426+00:00 | 0.613 |
| case | geometry.many-8.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:01.775775+00:00 | 0.670 |
| case | geometry.many-8.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:02.446192+00:00 | 0.668 |
| case | geometry.many-32.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:03.113890+00:00 | 0.835 |
| case | geometry.many-32.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:03.948572+00:00 | 0.832 |
| case | geometry.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:04.780641+00:00 | 0.687 |
| case | geometry.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:05.467902+00:00 | 0.688 |
| case | geometry.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:06.155906+00:00 | 0.917 |
| case | geometry.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:07.073255+00:00 | 0.941 |
| case | geometry.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:08.014123+00:00 | 0.684 |
| case | geometry.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:08.698540+00:00 | 0.680 |
| case | ancestor.depth-1.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:09.378717+00:00 | 0.648 |
| case | ancestor.depth-1.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:10.026972+00:00 | 0.651 |
| case | ancestor.width-16.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:10.677611+00:00 | 0.696 |
| case | ancestor.width-16.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:11.373718+00:00 | 0.697 |
| case | ancestor.width-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:12.070290+00:00 | 0.932 |
| case | ancestor.width-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:13.002593+00:00 | 0.942 |
| case | ancestor.sparse-64.columns.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:13.944406+00:00 | 0.708 |
| case | ancestor.sparse-64.document.typed | member=write-lowering, runtime=3.14, window=keyed-write | 2026-09-23T20:34:14.652637+00:00 | 0.701 |
| case | acquisition.rows-8.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-23T20:34:15.353949+00:00 | 1.324 |
| case | acquisition.rows-32.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-23T20:34:16.677905+00:00 | 3.030 |
| case | acquisition.rows-128.columns | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-23T20:34:19.707522+00:00 | 9.944 |
| case | acquisition.rows-8.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-23T20:34:29.651153+00:00 | 1.378 |
| case | acquisition.rows-32.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-23T20:34:31.029149+00:00 | 3.172 |
| case | acquisition.rows-128.document | member=write-lowering, runtime=3.14, window=predicate-acquisition | 2026-09-23T20:34:34.201466+00:00 | 10.321 |
| case | response.insert.family.wire | member=write-lowering, runtime=3.14, window=wire-insert-response | 2026-09-23T20:34:44.522202+00:00 | 0.603 |
| case | model.prepared | member=write-lowering, runtime=3.14, window=model-preparation | 2026-09-23T20:34:45.124765+00:00 | 4.232 |
| case | model.prepared.family | member=write-lowering, runtime=3.14, window=model-preparation | 2026-09-23T20:34:49.356461+00:00 | 0.807 |
