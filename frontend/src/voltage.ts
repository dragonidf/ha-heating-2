import type { Settings, VoltageSettings } from "./types";
export const voltageDefaults: Readonly<VoltageSettings> = Object.freeze({
  min_voltage_v: 190,
  max_voltage_v: 250,
  hysteresis_v: 5,
  stable_recovery_s: 30,
  voltage_max_age_s: 30,
});
export const voltageRanges: Readonly<
  Record<keyof VoltageSettings, readonly [number, number]>
> = {
  min_voltage_v: [80, 280],
  max_voltage_v: [120, 300],
  hysteresis_v: [0, 30],
  stable_recovery_s: [0, 600],
  voltage_max_age_s: [1, 300],
};
export const voltageKeys = Object.keys(
  voltageDefaults,
) as (keyof VoltageSettings)[];
export function voltageValues(
  values: Partial<VoltageSettings>,
): VoltageSettings {
  return { ...voltageDefaults, ...values };
}
export function validateVoltageSettings(
  values: Partial<VoltageSettings>,
): string[] {
  if (!voltageKeys.some((key) => Object.hasOwn(values, key))) return [];
  const errors: string[] = [];
  for (const key of voltageKeys) {
    const value = values[key],
      range = voltageRanges[key];
    if (
      typeof value !== "number" ||
      !Number.isFinite(value) ||
      value < range[0] ||
      value > range[1]
    )
      errors.push(`${key}: ${range[0]}–${range[1]}`);
  }
  const v = values as VoltageSettings;
  if (v.min_voltage_v >= v.max_voltage_v)
    errors.push("Мінімальна вхідна напруга має бути нижчою за максимальну");
  if (2 * v.hysteresis_v >= v.max_voltage_v - v.min_voltage_v)
    errors.push("Подвійний гістерезис має бути меншим за діапазон напруги");
  return errors;
}
export function withVoltageSettings(
  values: Settings,
  key: keyof VoltageSettings,
  value: number,
): Settings & VoltageSettings {
  return { ...voltageValues(values), ...values, [key]: value };
}
