# Heating AI 2.0 — production HA SHADOW candidate (no commands)

This is a **separate** Home Assistant custom integration, `heating_ai_v2`, outside the legacy `heating_ai` synthetic sandbox and outside the AppDaemon heating controller. It has no actuator, service call, app start/stop, automation or entity helper. The accepted original package and original home configuration remain untouched.

## Installation *after code review and approval*

1. Back up Home Assistant. **Use the reviewed CI ZIP artifact**, which contains the compiled UI and vendored verified engine. Extract only `custom_components/heating_ai_v2` into HA's `/config/custom_components/heating_ai_v2`, then restart HA. **Do not copy the source-tree folder alone:** it lacks required `assets/livePanel.js` and `engine/SOURCE-SHA256.json`. No install has been performed by this PR.
2. Settings → Devices & Services → Add Integration → **Heating AI 2.0 — read-only shadow**. Select the existing entities for the thermostat, living-room temperature, authoritative **input_select utility status helper** (\`Наявна мережа\` / \`Відсутня мережа\`), and **upstream** voltage sensors for three phases, direct KWS local L1/L2/L3 active power (each **kW**) and KWS local **total** energy (kWh).
3. The integration checks that the four KWS entities belong to **one** device on the `tuya_local` integration. The input_select is the ONLY authoritative Boolean grid-state input. Voltage sensors are last-known values and cannot override grid absence or an unknown helper state. It does not need cloud entities or any old derived helpers. If the selected upstream voltage source is downstream of KWS or inverter, that is **not** a commissioned voltage safety feed; shadow will display it but never grant heating.
4. **Phase assignment:** physical phase **1 → A, 2 → B, 3 → C** for both incoming input-220 voltages and local KWS power. Bind by the real channel, not by a reversed card caption. These incoming voltage values can remain cached after blackout; ONLY the existing input_select helper determines grid present/absent.
5. Optionally bind boiler return-line external probe, direct fireplace temperature, ONE local circulation fan entity, existing fan-mode and three speed helpers, verified-backup and fan-control helpers, recuperator and bathroom extractor relay. The extras are read-only. Missing extras stay unknown rather than inventing a fire or an on/off state.
6. Circulation policy reuses the accepted pure `fan_policy` (heat delta 5°C, hold until 3°C/cooldown, manual stop priority, night/day/intense 38/42/45% when configured). In SHADOW, the result is a *proposal only*: zero fan commands. The backup_verified helper by itself does not prove live inverter power; without independent proof, the new observer conservatively proposes no fan activation on outage.
7. The existing circulation automation, fireplace controller, recup and extractor timers remain untouched; a real cutover needs exclusive fan ownership as well as exclusive thermostat ownership.
8. Read the four new entities (mode, temperature, KWS power, KWS energy). Mode should always be `SHADOW`; `commands_enabled=false`, `physical_ack=false`. Compare values to the original KWS entities and current old heating dashboard. A stale unchanged phase reading of 0 kW stays a **last-known** display value. Missing or invalid phase → power unknown. No 3/6/9 mode is claimed without calibration.
5. Rollback: remove this *separate* integration in Devices & Services; restart after removing only its new files if desired. Never disable the shared AppDaemon or delete existing old Heating AI entities to run SHADOW.

## Deliberate limitations

- This is a read-only **integration prototype**, not the functioning Heating AI 2.0 controller. It **does not calculate or execute heating plans**, nor establish trust in a hardware heartbeat. No thermal/electrical safety authorization or physical relay state can be inferred from HA states.
- HA last_reported, source availability, KWS cached 0 kW and a successful climate service call (when added in a later reviewed stage) are not physical proof of opened/closed dry contacts.
- This standalone profile is not the old HACS integration. Do not assume its folder can be installed by pointing the old HACS repository at it; the rollout uses a separate reviewed install route.
- Next deliverable: bridge the accepted controller/planner/critical owner ledger into the real profile in a **separate explicit command boundary**, OFF by default, and prove an exclusive writer and rollback before any live actuation.

## Safety tests

`python -m unittest tests.wp2c_revision.test_live_shadow_v2 -v` should pass with no Home Assistant dependency. The existing sealed synthetic package remains immutable and retains all of its original boundary tests. Passing these unit checks is **not** proof that HA 2026.11 integration setup completed; the physical-install stage must verify that separately.

## Stability and safety

- The v2 observation keeps bounded in-memory fan state only. Restarts do not re-arm heating or automatically replay pending fan commands. Persistent errors log once per fault episode instead of flooding the logger. There is exactly one periodic safety observer (60s), cleaned up on entry unload.
- `fan.tsirkuliatsiia_povitria_lokal` should be bound as the **single** circulation fan; its cloud alias refers to the same physical device and is not an independent witness. Existing `Зупинити` mode must be preserved, not overwritten by v2 setup.
- This release remains read-only, not the full P0/P1 controller. Shadow running state and manual cutover are separate acceptance gates; the legacy fan and boiler automations remain active until supervised ownership transfer.


## Real future-source inputs (native HA, zero services)

Optional roles `weather_forecast` and `outage_calendar` bind an existing HA
WeatherEntity with hourly support and an existing timetable calendar. The v2
SHADOW subscribes directly to WeatherEntity hourly updates and uses the native
CalendarEntity async_get_events read API, once every 30 minutes at most; there
is **no service registry or device command path**. Invalid/missing providers
yield UNKNOWN, never fresh evidence or an assumed grid-on window.

Important: HA weather forecast returns an hourly temperature series but generally
does not expose the provider's original forecast issuance time. We retain the
actual v2 receipt time and mark issuance UNKNOWN. The outage calendar gives
explicit off events, not guaranteed normal-grid coverage outside those events.
Do not execute the optimizer's physical plan on these inputs before G4/G5/G6.
