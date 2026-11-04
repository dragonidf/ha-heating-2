# WP2B contract fixtures and fake operation boundary

All IDs begin synthetic where an identifier is needed; no household source/telemetry/configuration is used. `tools/wp2b/export_contracts.py` exports actual unchanged WP2A dataclasses through encode/decode: StatusView, acknowledged status, saved/unavailable APIReceipt, a frozen ForecastRecord and its latest source, and BudgetReceipt. Recreate at repository root with `python -m tools.wp2b.export_contracts`; CI `--check` requires exact bytes. Generated JSON is excluded from prettier to preserve canonical export formatting. SHA256SUMS binds both exporter and result.

TS adapters validate envelope major2, finite values, allowed statuses and actual/physical flag. Frozen and source curves must match; source receipt is retained separately from original freeze invocation. Original eligibility checks both issue/receipt and actual time coverage. Budget reference requires scope; estimated energy is a separate explicit artificial projection, not an inferred field from BudgetReceipt.

The frontend UI1 projection is deliberately separate from future native transport:

| Operation | Synthetic behavior | Limit |
|---|---|---|
| Status subscription | ordered seq+generation; stale/replay ignored; gap disconnects; full reconnect required | one cached snapshot, no socket/timer loop |
| History | immutable artificial points, stable scoped cursor/watermark |128default/256max per page;64KiB/page;100000 raw/query;≤4000 overview/4096render limit; full scoped traversal |
| Settings get/save | typed UI comfort/settings projection, in-process capability, expected revision, IndexedDB transaction/readback | no real ControlPolicy configuration route |
| Receipt | actual WP2A status/persisted revision semantics; client checks ID/generation/version/readback | saved is local desired UI state only |
| Pause/resume/one-shot | explicit fake intents and distinct unknown/expired/cancelled/consumed states | no sender; no auto HEAT after resume/reload |
| Model | fixed qualified synthetic challenger example, promote/freeze/rollback procedure | not actual fit, backend learning or physical readiness |
| Errors | stale/missing/offline, safety/manual/grid/anomaly, false ACK, storage/timeout/readback, conflict/revoke/replay/gap | controls fail closed; draft retained |

A second browser window uses the same isolated origin's settings DB and genuine readwrite CAS. Request retries are idempotent only for the matching current request/body; unknown write acknowledgement can require reread and explicit rebase. Fake capability possession is not real authentication. Client hiding is not authorization: mock checks at commit; a later real server must enforce its own permission/ownership gate.

Scenario switching selects a new isolated synthetic example; it does not mutate a real archive. Historical original bytes are never recomputed from model changes. UI1 settings/history schema is new demo code, not claimed native HA/WS compatibility. Backend351 tests and source hashes remain the accepted authority for actual safety/store/energy invariants.


Review correction contracts

- Settings merge retains the editable base and derives dirty leaf paths. Recursive base/local/remote comparison covers all12 present fields plus future nested JSON objects; arrays are atomic, absence differs from null. Same-field divergence blocks save until an explicit choice. Undo rebases its old local patch onto the current base; reread never blindly replaces a dirty draft. A quick replacement save cannot discard a dirty draft. Save receipts retain the accepted API semantics.
- Point `coverage:{source,from}` certifies continuity from an earlier historical timestamp for the same qualified source; it is not a sensor value or an operational freshness threshold. Only a trusted synthetic cadence policy produces this metadata here: hourly normal and five-minute dense fixtures. Unknown cadence has no continuity proof. Non-valid `quality` cannot appear as a measured actual value. Derived `gap:{start,end,seconds,count}` is a null annotation, visibly unknown, never a reconstructed reading.
- Full-range query consumes scoped immutable pages, validates watermark/monotone cursor/order/finite time, and retains first/last/min/max/null representatives in800 fixed UTC bins. Different sources/runs cannot be connected after aggregation or chart decimation. Total unknown duration and unqualified-edge count use the full stream; individual gap annotations are representative when several occupy one bin. The accessible overview table can load further overview rows. Raw archives above100000 readings fail explicitly; no partial oldest-range result is presented as complete.
- EnergyInterval optional `method` distinguishes aggregate `counter_difference` (also the conservative default for absent method), qualified `integrated_power`, and `prorated_estimate`. An integrated slice denotes already qualified uniform timestamped power integration under WP2A semantics; category `derived` alone does not grant that assumption. Scope ends at min(query.end, actualUntil). Partial aggregate/recovered clipping is proportionally allocated only as estimated, never measured. Optional dated tariff windows override a single uniform `price`; overlapping or invalid tariffs/energy intervals fail closed. Counter amounts split across tariff changes and recovered costs remain estimated. Energy and cost quantities, quality and coverage are tracked separately, including unpriced kWh/unknown minutes and genuine zero cost.
- Scenario `dense-history` adds a deeply frozen synthetic five-minute archive with extrema/gaps plus a1kWh counter spanning Kyiv23:50–00:10 and a tariff switch at midnight. It is artificial QA data, not household evidence. The old hourly fixture, immutable original and all accepted Python contracts are retained.


Follow-up isolation/time contract (review6625889290)

- Temperature and energy/cost are independent guarded read results; errors remain with their domain. A failed energy result is null and cannot be rendered as a known-zero summary. A date-validation error affects the whole query. Reconnect generation invalidates both cached results; disconnected cached data retains its explicit label.
- `readHistory` quarantines every finite in-range raw observation with `at > snapshot.now`, with no tolerance. Raw count includes quarantine rows; `quarantinedCount` reports them, but overview values/gap annotations/coverage never include their future timestamps. Exact now is inclusive. Ordering/progress/page/watermark/capacity checks still apply to the entire raw stream. Archives are not mutated, repaired or backfilled.
- Chart actual input independently rejects nonfinite/future timestamps and maps explicit non-valid quality to unknown before calculating axes, paths, markers, table and cursor. A future forecast remains a forecast with actual unknown. Optional absent quality preserves the accepted legacy Point value semantics; explicit null/empty/unrecognised quality fails closed. Source-qualified cadence is still required to connect observations, and no optional quality grants physical verification.
- New fake scenarios `energy-error`, `temperature-error`, `future-history` expose malformed energy overlap, a temperature read fault, and deeply frozen past/estimated/exact-now/future records. These are isolated test fixtures with no external transport.
