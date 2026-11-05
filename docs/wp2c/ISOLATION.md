# Isolation and reproducible disposable HA

The harness accepts no HA URL, host credentials, device address or existing Docker endpoint. It always clears Docker context/TLS overrides and uses the sandbox local daemon socket. New UUID-prefixed `wp2c-*` container/volumes have an ownership label; teardown checks labels before removing only those resources. No owner infrastructure or old repository is used.

Runtime isolation:

- HA `--network none`, no PortBindings, loopback127.0.0.1:8123 only; no host network/public port/privileged mode/socket mount.
- Capabilities dropped ALL, no-new-privileges, bounded process count, two disposable volumes (`/config`, `/tmp`). A separate setup-only network-none helper normalizes ownership of only these volumes; running HA remains capability-restricted.
- No default_config, ZeroConf, SSDP, DHCP, Bluetooth, MQTT, ZHA, Tuya, cloud or weather clients. Onboarding non-user optional steps are preseeded in the new empty config to avoid HA's optional cloud defaults; the exact loopback-only HTTP trial is explicitly confirmed through its native admin API (no pending5minute rollback); first-user onboarding, authorization-code exchange, reader creation and normal browser login remain actual HA flows.
- Random synthetic credentials stay mode600 inside the disposable volume. Browser helper passes them through stdin to its process, never PR files/argv/trace. Native browser trace is OFF; artifacts contain synthetic UI screenshots and redacted results only. Auth `.storage`, secret files and tokens are excluded.
- Browser container joins `container:<new-HA>` namespace, has no network of its own, mounts only reviewed frontend tooling read-only and writes results to tmpfs. Existing HA session is injected into the panel; no panel-owned transport/token storage.
- Proof reads namespace routes/listeners and Docker restrictions; negative connect tests target only documentation-reserved192.0.2/198.51.100/203.0.113 addresses and unused loopbackport9. They never probe private/home LAN. All connections must fail. Public dependency retrieval is confined to setup; runtime proxy variables are empty.

## Reproduction

Use a disposable Linux runner with Docker, C compiler, Python, Node24.19 and sufficient storage. Never run this recipe on owner equipment. At repository root:

```sh
npm ci --ignore-scripts --prefix frontend
npm run build --prefix frontend
node tools/wp2c/export-fixtures.mjs --check
python tools/wp2c/package.py --output /tmp/heating-wp2c-package-ci
python -m unittest tools.wp2c.test_package tools.wp2c.test_browser_outputs
python tools/wp2c/sandbox.py build
docker --host=unix:///var/run/docker.sock pull mcr.microsoft.com/playwright:v1.64.1-noble@sha256:2f05f8a734509a7b3f26a912639488ee08f58a7b292d14d62271bcff9038768f
python tools/wp2c/sandbox.py up --state /tmp/wp2c-sandbox.json --package-dir /tmp/heating-wp2c-package-ci
python tools/wp2c/sandbox.py typecheck --state /tmp/wp2c-sandbox.json
python tools/wp2c/sandbox.py checks --state /tmp/wp2c-sandbox.json
python tools/wp2c/sandbox.py restart --state /tmp/wp2c-sandbox.json
python tools/wp2c/sandbox.py migration --state /tmp/wp2c-sandbox.json
python tools/wp2c/sandbox.py browser --state /tmp/wp2c-sandbox.json --project chromium
python tools/wp2c/sandbox.py browser --state /tmp/wp2c-sandbox.json --project webkit
python tools/wp2c/sandbox.py proof --state /tmp/wp2c-sandbox.json
python tools/wp2c/sandbox.py stop --state /tmp/wp2c-sandbox.json
```

Always execute `stop` in a finally/CI-always step. Only generated package artifacts are copied into this new instance. Do not copy private configuration or point the harness at an existing volume. Local generated image IDs vary with dependency build metadata; exact pinned source hashes and each actual image ID are recorded. CI uses the final PR head and retains sanitized evidence for14days. Short synthetic host measurements do not qualify N100, electrical OFF latency or a7day/3cycle household shadow.

Before browsers, a short-lived labeled helper with only NET_ADMIN creates a veth pair whose **two ends remain in the same new HA namespace**. It has no host/bridge/external peer. A documentation-only192.0.2.254/32 address uses NOPREFIXROUTE; the main IPv4 routing table must remain empty. Both peer indices are verified in that namespace before and after browsers, and the existing negative transport/listener checks remain mandatory. The helper exits immediately; HA and browser keep cap-drop ALL. This supplies an actual local link for browser network hints without adding an external route. GIO's base network monitor is selected only in the browser; native E2E still require actual offline inhibition and authoritative reconnect. No JavaScript navigator override is installed.
