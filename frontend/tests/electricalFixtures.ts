import type { VoltageView } from "../src/types";
import { voltageDefaults } from "../src/voltage";
export function qualifiedVoltage(): VoltageView {
  return {
    status: "NORMAL",
    eligible: true,
    affected_phases: [],
    reason: "synthetic qualified phases",
    ages: { L1: 0, L2: 0, L3: 0 },
    phases: (["L1", "L2", "L3"] as const).map((phase) => ({
      phase,
      voltage_v: 230,
      age_s: 0,
      online: true,
      qualified: true,
    })),
    limits: { ...voltageDefaults },
    source_role: "grid_input_voltage",
    source_provider: "zigbee2mqtt_input220",
    physical_authority: false,
    scope: "synthetic_only",
  };
}
