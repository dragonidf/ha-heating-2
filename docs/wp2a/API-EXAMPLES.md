# WP2A typed API examples — fake/worker only

These are Python value boundaries for a future frontend/transport, not enabled HTTP/WebSocket/HA endpoints. `encode`/`decode` use strict envelope2.0 and the supported record type. Only artificial fixture handles are supported. A serialized permission record is not a `FakeSession` capability.

```python
# In the isolated fixture harness, with explicit injected Clock:
status = runtime.status(read_session, clock)  # StatusView: actual may be None
assert status.physical_verified is False
receipt = runtime.save(save_request, admin_session, clock)
# Only receipt.status == "saved" includes a durable persisted_revision.

# Future compute consumes normalized typed source inputs; never returns a device call:
proposal = runtime.plan(request, previous_proposal)
runtime.queue_forecast(proposal, request, "synthetic.cycle", reference, role="latest")
# Queued only; explicit archive worker persists proposal and scoped curve lineage.
runtime.accept(proposal, clock)  # bridge + accepted WP1A/WP1B checks, fake only
runtime.pump(clock)             # only the existing in-memory FakeActuator
runtime.trusted_stop(clock)     # no evidence/critical-store reads

# Explicit archive worker; never call from the safety/HA event loop:
runtime.flush_evidence()
page = evidence.query("synthetic.heat", "PowerPoint", start, end, limit=256)
next_page = evidence.query("synthetic.heat", "PowerPoint", start, end,
                           limit=256, cursor=page.cursor)
# Only continue when page.cursor is non-null; it binds scope and archive prefix.
summary = evidence.summary("synthetic.heat")
# summary.actual_total_kwh excludes estimated_kwh; unknown_s is independent.
budget = evidence.budget("synthetic.cycle", "synthetic.heat", end, projected_total)
# reference is immutable; end is the actual-spend cutoff, receipt.scope is the
# full forecast energy period. Unscoped old amounts are not verified references.
# known_remaining is conditional on unknown_s coverage.

preview = runtime.recovery(request, "synthetic.heat", backup_root,
                           admin_session, dry_run=True)
result = runtime.recovery(request, "synthetic.heat", backup_root,
                          admin_session, dry_run=False)
# Before taking that disposable backup, archive two independent/direct VALID KWH
# Readings and a RecoveryProof binding their IDs, gap IDs, exact window and delta.
# request.evidence_hash = checksum(encode(proof)); archive proof under that digest.
# Apply/preview independently check proof and raw counter arithmetic, plus current
# total/head, exact disposable backup, admin authority and unique unknown claims.
# Missing/unqualified proof is rejected; approval cannot supply missing metrology.

manifest = dry_run(synthetic_legacy_bundle)  # no writes
receipt = stage(manifest, empty_disposable_evidence)
rollback = rollback_copy(manifest, evidence, another_disposable_root)
assert not rollback.bundle.policy.armed  # history/consumed intents carried forward
```

Registry/config revision, model/topology and owner/boot/grid fencing are separate from cursor/watermark and energy continuity. All timestamps are injected UTC seconds; calendar policy receives an explicit timezone. Dated tariff and source/coverage metadata remain part of data, never inferred from a current price or current reading. UI, native HA services and production transport are outside WP2A.

A queued forecast receives a verified energy_scope only for a reference inside the complete simulated horizon with qualified request-stage power. Its amount integrates segment overlap from reference onward; it excludes earlier plan energy. Outside/absent coverage has planned_kwh=None and energy_scope=None. Existing unscoped archived amounts remain unverified. A fresh thermostat author assertion can establish an ownership-uncertain pause without any Reading; its observed_action and author fields never authenticate a physical action. Healthy readings alone do not clear that pause.

For `evidence.freeze_original(cycle, reference, as_of=...)`, an eligible latest source must have both curve.issued and recorded_at <= reference−43200, and recorded_at <= as_of. The original's recorded_at records invocation time, which can be later; it does not backdate source availability. Missing evidence freezes as MISSING permanently. Repeated calls return the immutable original without changing the archive, even after newer or backdated synthetic arrivals. This does not validate imported historical originals or authenticate a real provider clock.
