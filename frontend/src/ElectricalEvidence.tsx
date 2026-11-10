import { Card, Badge } from "./components";
import { fmt } from "./domain";
import type { Snapshot, VoltageStatus } from "./types";
const labels: Record<VoltageStatus, string> = {
  LOW: "Вхідна напруга нижча за межу",
  HIGH: "Вхідна напруга вища за межу",
  MISSING_OR_STALE: "Немає всіх свіжих фаз",
  STABILIZING: "Очікуємо стабільне відновлення",
  NORMAL: "Вхідна напруга в межах",
};
export function ElectricalEvidence({ state }: { state: Snapshot }) {
  const voltage = state.voltage,
    power = state.power;
  return (
    <>
      <Card
        title="Вхідна напруга мережі"
        aside={
          <Badge tone={voltage?.eligible ? "control" : "warning"}>
            {voltage?.status ?? "MISSING_OR_STALE"}
          </Badge>
        }
      >
        <p>
          {labels[voltage?.status ?? "MISSING_OR_STALE"]}.{" "}
          {voltage?.reason ??
            "Немає кваліфікованих синтетичних звітів вхідних фаз."}
        </p>
        <p>
          Джерело: Zigbee2MQTT input 220 · вхід мережі. Не вимір напруги на
          клемах котла; дані інвертора не замінюють відсутню фазу.
        </p>
        <p>
          Запит нагріву:{" "}
          {state.demand_eligible === true
            ? "лише допустимий у симуляції"
            : "заблокований захистами"}
          . Це не команда HEAT і не доказ фізичної дії.
        </p>
        <div
          className="table-scroll"
          role="region"
          aria-label="Синтетичні звіти вхідних фаз"
          tabIndex={0}
        >
          <table>
            <caption>Синтетичні звіти вхідних фаз</caption>
            <thead>
              <tr>
                <th>Фаза</th>
                <th>Вхідна напруга · В</th>
                <th>Вік звіту · с</th>
                <th>Докази</th>
              </tr>
            </thead>
            <tbody>
              {(["L1", "L2", "L3"] as const).map((phase) => {
                const row = voltage?.phases.find((p) => p.phase === phase);
                return (
                  <tr key={phase}>
                    <th scope="row">{phase}</th>
                    <td>{fmt(row?.qualified ? row.voltage_v : null)}</td>
                    <td>{fmt(row?.age_s ?? null)}</td>
                    <td>
                      {row?.qualified
                        ? "кваліфікований синтетичний звіт"
                        : "невідомо / застаріле"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {voltage && (
          <p>
            Межі: {fmt(voltage.limits.min_voltage_v)}–
            {fmt(voltage.limits.max_voltage_v)} В · гістерезис{" "}
            {fmt(voltage.limits.hysteresis_v)} В · стабільність{" "}
            {fmt(voltage.limits.stable_recovery_s, 0)} с · вік не більше{" "}
            {fmt(voltage.limits.voltage_max_age_s, 0)} с. Уражені фази:{" "}
            {voltage.affected_phases.join(", ") || "—"}.
          </p>
        )}
        <p className="helper">
          Мітки фаз синтетичні; фізичне зіставлення не підтверджене. Відновлення
          повертає лише допустимість запиту та не скасовує ручну паузу.
          Програмний контроль не замінює незалежний апаратний захист KWS, насос
          чи OEM-захисти. G1/B01–B08 BLOCKED.
        </p>
      </Card>
      <Card
        title="Потужність та лічильник котла"
        aside={<Badge tone="warning">{power?.stage ?? "UNKNOWN"}</Badge>}
      >
        <p>
          Оцінка ступеня за узгодженими активними потужностями та витримкою
          часу. {power?.reason ?? "Кваліфікованих звітів KWS немає."}
        </p>
        <p>
          Джерело: KWS через Tuya Local · окремий облік котла. Хмарна копія Tuya
          не додається та не підміняє локальне джерело.
        </p>
        <dl className="diagnostic-list">
          <dt>Сумарна активна потужність · Вт</dt>
          <dd>{fmt(power?.total_active_w ?? null, 0)}</dd>
          <dt>Єдиний загальний імпортований лічильник · кВт·год</dt>
          <dd>{fmt(power?.total_imported_kwh ?? null, 3)}</dd>
        </dl>
        <div
          className="table-scroll"
          role="region"
          aria-label="Синтетична активна потужність KWS"
          tabIndex={0}
        >
          <table>
            <caption>Синтетична активна потужність KWS</caption>
            <thead>
              <tr>
                <th>Фаза</th>
                <th>Активна потужність · Вт</th>
                <th>Вік звіту · с</th>
              </tr>
            </thead>
            <tbody>
              {(["L1", "L2", "L3"] as const).map((phase) => {
                const row = power?.phases.find((p) => p.phase === phase);
                return (
                  <tr key={phase}>
                    <th scope="row">{phase}</th>
                    <td>{fmt(row?.active_w ?? null, 0)}</td>
                    <td>{fmt(row?.age_s ?? null)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="helper">
          Усі звіти синтетичні. Стан реле не доводить нагрів; ступінь не є
          фізичним підтвердженням. Немає припущення про однакові ТЕНи чи 3 кВт
          на фазу. UNKNOWN означає невідомий ступінь, не нуль.
        </p>
        <p className="helper">
          Загальні кВт·год рахуються один раз; фазні лічильники — лише
          перевірка. Незмінний показ без кваліфікованого heartbeat не доводить
          нульову витрату. VA, струм чи стан реле не замінюють активну енергію.
          Реле KWS не є програмним виконавцем. G1/B03 BLOCKED.
        </p>
      </Card>
    </>
  );
}
