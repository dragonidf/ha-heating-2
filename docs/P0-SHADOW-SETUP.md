# Heating AI 2.0 — production HA SHADOW candidate (no commands)

This is a **separate** Home Assistant custom integration, `heating_ai_v2`, outside the legacy `heating_ai` synthetic sandbox and outside the AppDaemon heating controller. It has no actuator, service call, app start/stop, automation or entity helper. The accepted original package and original home configuration remain untouched.

## Installation *after code review and approval*

1. Back up the Home Assistant configuration. Copy only the folder `releases/ha_v2/custom_components/heating_ai_v2` into HA's `/config/custom_components/heating_ai_v2`; restart HA. No install has been performed by this PR.
2. Settings → Devices & Services → Add Integration → **Heating AI 2.0 — read-only shadow**. Select the existing entities for the thermostat, living-room temperature, authoritative **input_select utility status helper** (\`Наявна мережа\` / \`Відсутня мережа\`), and **upstream** voltage sensors for three phases, direct KWS local L1/L2/L3 active power (each **kW**) and KWS local **total** energy (kWh).
3. The integration checks that the four KWS entities belong to **one** device on the `tuya_local` integration. The input_select is the ONLY authoritative Boolean grid-state input. Voltage sensors are last-known values and cannot override grid absence or an unknown helper state. It does not need cloud entities or any old derived helpers. If the selected upstream voltage source is downstream of KWS or inverter, that is **not** a commissioned voltage safety feed; shadow will display it but never grant heating.
4. Read the four new entities (mode, temperature, KWS power, KWS energy). Mode should always be `SHADOW`; `commands_enabled=false`, `physical_ack=false`. Compare values to the original KWS entities and current old heating dashboard. A stale unchanged phase reading of 0 kW stays a **last-known** display value. Missing or invalid phase → power unknown. No 3/6/9 mode is claimed without calibration.
5. Rollback: remove this *separate* integration in Devices & Services; restart after removing only its new files if desired. Never disable the shared AppDaemon or delete existing old Heating AI entities to run SHADOW.

## Deliberate limitations

- This is a read-only **integration prototype**, not the functioning Heating AI 2.0 controller. It **does not calculate or execute heating plans**, nor establish trust in a hardware heartbeat. No thermal/electrical safety authorization or physical relay state can be inferred from HA states.
- HA last_reported, source availability, KWS cached 0 kW and a successful climate service call (when added in a later reviewed stage) are not physical proof of opened/closed dry contacts.
- This standalone profile is not the old HACS integration. Do not assume its folder can be installed by pointing the old HACS repository at it; the rollout uses a separate reviewed install route.
- Next deliverable: bridge the accepted controller/planner/critical owner ledger into the real profile in a **separate explicit command boundary**, OFF by default, and prove an exclusive writer and rollback before any live actuation.

## Safety tests

`python -m unittest tests.wp2c_revision.test_live_shadow_v2 -v` should pass with no Home Assistant dependency. The existing sealed synthetic package remains immutable and retains all of its original boundary tests. Passing these unit checks is **not** proof that HA 2026.11 integration setup completed; the physical-install stage must verify that separately.
