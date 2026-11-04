# WP2B contract fixtures and fake operation boundary

All IDs begin synthetic where an identifier is needed; no household source/telemetry/configuration is used. `tools/wp2b/export_contracts.py` exports actual unchanged WP2A dataclasses through encode/decode: StatusView, acknowledged status, saved/unavailable APIReceipt, a frozen ForecastRecord and its latest source, and BudgetReceipt. Recreate at repository root with `python -m tools.wp2b.export_contracts`; CI `--check` requires exact bytes. Generated JSON is excluded from prettier to preserve canonical export formatting. SHA256SUMS binds both exporter and result.

TS adapters validate envelope major2, finite values, allowed statuses and actual/physical flag. Frozen and source curves must match; source receipt is retained separately from original freeze invocation. Original eligibility checks both issue/receipt and actual time coverage. Budget reference requires scope; estimated energy is a separate explicit artificial projection, not an inferred field from BudgetReceipt.

The frontend UI1 projection is deliberately separate from future native transport:

| Operation | Synthetic behavior | Limit |
|---|---|---|
| Status subscription | ordered seq+generation; stale/replay ignored; gap disconnects; full reconnect required | one cached snapshot, no socket/timer loop |
| History | immutable artificial points, stable scoped cursor/watermark |128default/256max per page;4096render input;32pages |
| Settings get/save | typed UI comfort/settings projection, in-process capability, expected revision, IndexedDB transaction/readback | no real ControlPolicy configuration route |
| Receipt | actual WP2A status/persisted revision semantics; client checks ID/generation/version/readback | saved is local desired UI state only |
| Pause/resume/one-shot | explicit fake intents and distinct unknown/expired/cancelled/consumed states | no sender; no auto HEAT after resume/reload |
| Model | fixed qualified synthetic challenger example, promote/freeze/rollback procedure | not actual fit, backend learning or physical readiness |
| Errors | stale/missing/offline, safety/manual/grid/anomaly, false ACK, storage/timeout/readback, conflict/revoke/replay/gap | controls fail closed; draft retained |

A second browser window uses the same isolated origin's settings DB and genuine readwrite CAS. Request retries are idempotent only for the matching current request/body; unknown write acknowledgement can require reread and explicit rebase. Fake capability possession is not real authentication. Client hiding is not authorization: mock checks at commit; a later real server must enforce its own permission/ownership gate.

Scenario switching selects a new isolated synthetic example; it does not mutate a real archive. Historical original bytes are never recomputed from model changes. UI1 settings/history schema is new demo code, not claimed native HA/WS compatibility. Backend351 tests and source hashes remain the accepted authority for actual safety/store/energy invariants.
