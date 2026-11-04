import type {
  APIReceipt,
  HistoryCursor,
  HistoryPage,
  Scenario,
  Settings,
  Snapshot,
  Window,
} from "./types";
import type { SettingsStore } from "./storage";
import { snapshot, actual } from "./fixtures";
import { readReceipt } from "./contracts";
import { validateSettings, withDeadline } from "./domain";
export class SnapshotFeed {
  private listeners = new Set<() => void>();
  value: Snapshot;
  constructor(value: Snapshot) {
    this.value = structuredClone(value);
  }
  subscribe = (fn: () => void) => {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  };
  private notify() {
    for (const fn of this.listeners) fn();
  }
  reset(value: Snapshot) {
    this.value = structuredClone(value);
    this.notify();
  }
  accept(next: Snapshot): boolean {
    if (next.generation !== this.value.generation || next.seq <= this.value.seq)
      return false;
    if (next.seq !== this.value.seq + 1) {
      this.value = { ...this.value, connected: false };
      this.notify();
      return false;
    }
    this.reset(next);
    return true;
  }
}
export class DemoAPI {
  readonly session = Object.freeze({ synthetic: true });
  readonly feed = new SnapshotFeed(snapshot());
  fault: "none" | "write" | "readback" | "timeout" = "none";
  scenario: Scenario = "normal";
  private requestCounter = 0;
  private pending = false;
  model = { revision: 3, candidate: false, frozen: false };
  modelAction(
    kind: "train" | "promote" | "rollback" | "freeze",
    session: object,
  ): string {
    if (session !== this.session || !this.canChange())
      return "Операцію відхилено";
    if (kind === "freeze") this.model.frozen = !this.model.frozen;
    else if (this.model.frozen && kind !== "rollback")
      return "Навчання заморожено";
    else if (kind === "train") this.model.candidate = true;
    else if (kind === "promote") {
      if (!this.model.candidate) return "Недостатньо доказів";
      this.model.revision = 4;
      this.model.candidate = false;
    } else this.model.revision = 3;
    const next = structuredClone(this.feed.value);
    next.seq++;
    this.feed.accept(next);
    return "Оновлено лише синтетичний приклад; історія незмінна";
  }

  constructor(
    private readonly store: SettingsStore,
    private readonly latency = 60,
  ) {}
  canChange(): boolean {
    const s = this.feed.value;
    return (
      s.connected &&
      s.permitted &&
      s.room.quality === "valid" &&
      s.now - s.room.observed <= 30 &&
      s.status.mode !== "SAFE_HOLD" &&
      s.status.mode !== "RECOVERING"
    );
  }
  async settings() {
    return withDeadline(this.store.read());
  }
  requestId() {
    return `synthetic.ui.${this.feed.value.generation}.${++this.requestCounter}.${crypto.randomUUID()}`;
  }
  setScenario(s: Scenario) {
    this.scenario = s;
    const old = this.feed.value;
    this.feed.reset(snapshot(s, old.seq + 1, old.generation));
  }
  reconnect() {
    const s = this.feed.value;
    this.scenario = "normal";
    this.feed.reset(snapshot("normal", s.seq + 1, s.generation + 1));
  }
  async save(
    id: string,
    expected: number,
    values: Settings,
    session: object,
  ): Promise<APIReceipt> {
    if (
      typeof id !== "string" ||
      id.length < 1 ||
      id.length > 128 ||
      !Number.isSafeInteger(expected) ||
      expected < 1
    )
      throw Error("Некоректний запит збереження");
    const receipt = (
      status: APIReceipt["status"],
      revision: number,
      reason: string,
    ) =>
      readReceipt({
        version: [2, 0],
        type: "APIReceipt",
        data: {
          request_id: id,
          status,
          revision,
          persisted_revision: status === "saved" ? revision : null,
          reason,
        },
      });
    if (session !== this.session || !this.feed.value.permitted)
      return receipt("denied", expected, "Доступ відкликано");
    if (!this.canChange() || this.pending)
      return receipt(
        "unavailable",
        expected,
        "Немає свіжого дозволеного стану",
      );
    if (validateSettings(values).length)
      return receipt("denied", expected, "Налаштування не пройшли перевірку");
    this.pending = true;
    let active = true;
    const generation = this.feed.value.generation;
    try {
      await new Promise((resolve) =>
        setTimeout(resolve, this.fault === "timeout" ? 100 : this.latency),
      );
      if (this.fault === "timeout")
        return receipt("unavailable", expected, "Час очікування вичерпано");
      if (this.fault === "write") throw Error("Збій локального запису");
      const result = await withDeadline(
        this.store.commit(
          expected,
          id,
          structuredClone(values),
          () =>
            active &&
            this.canChange() &&
            generation === this.feed.value.generation &&
            session === this.session,
        ),
      );
      if (result.conflict)
        return receipt(
          "conflict",
          result.state.revision,
          "Налаштування змінилися в іншому вікні",
        );
      const readback = await withDeadline(this.store.read());
      if (
        this.fault === "readback" ||
        !this.canChange() ||
        generation !== this.feed.value.generation ||
        readback.revision !== result.state.revision ||
        JSON.stringify(readback.values) !== JSON.stringify(values)
      )
        throw Error("Читання записаного стану не підтверджене");
      const projected = structuredClone(this.feed.value);
      projected.seq++;
      projected.status.status_seq++;
      if (projected.status.mode !== "MANUAL_PAUSE")
        projected.status.mode =
          values.mode === "observation"
            ? "SHADOW"
            : projected.status.mode === "SHADOW"
              ? "AUTO_HOLD"
              : projected.status.mode;
      if (values.mode === "observation")
        projected.status.desired = "stop_demand";
      if (values.circulation === "manual") projected.fan.requested = values.fan;
      if (values.circulation === "stop") projected.fan.requested = 0;
      this.feed.accept(projected);
      return receipt("saved", readback.revision, "Збережено лише в симуляції");
    } catch {
      return receipt(
        "unavailable",
        expected,
        "Запис або перевірку не підтверджено. Перевірте збережений стан.",
      );
    } finally {
      active = false;
      this.pending = false;
    }
  }
  control(
    kind:
      "pause" | "resume" | "arm" | "cancel" | "expire" | "unknown" | "consume",
    session: object,
  ): APIReceipt {
    const s = this.feed.value;
    if (session !== this.session || !this.canChange())
      return {
        request_id: this.requestId(),
        status: "denied",
        revision: 0,
        persisted_revision: null,
        reason: "Запит симуляції недоступний",
      };
    if (
      kind === "consume" &&
      (s.oneShot.state !== "armed" ||
        s.grid !== true ||
        s.status.mode === "MANUAL_PAUSE" ||
        s.status.mode === "SHADOW" ||
        s.oneShot.expires === null ||
        s.now >= s.oneShot.expires)
    )
      return {
        request_id: this.requestId(),
        status: "denied",
        revision: 0,
        persisted_revision: null,
        reason: "Немає кваліфікованого одноразового запиту",
      };
    const next = structuredClone(s);
    next.seq++;
    next.status.owner_epoch++;
    next.status.status_seq++;
    if (kind === "pause" || kind === "resume") {
      next.status.mode = kind === "pause" ? "MANUAL_PAUSE" : "RECOVERING";
      next.status.desired = "stop_demand";
      next.notices =
        kind === "pause"
          ? [
              {
                priority: "manual",
                text: "Автоматика на паузі. Запит змінює лише симуляцію.",
              },
            ]
          : [
              {
                priority: "quality",
                text: "Явний запит продовження прийнято. Потрібні нові дані й узгодження; старий нагрів не повторюється.",
              },
            ];
    } else {
      if (next.oneShot.state === "unknown_outcome" && kind === "arm")
        return {
          request_id: this.requestId(),
          status: "denied",
          revision: 0,
          persisted_revision: null,
          reason: "Невідомий результат не можна повторити",
        };
      next.oneShot = {
        state:
          kind === "arm"
            ? "armed"
            : kind === "cancel"
              ? "cancelled"
              : kind === "expire"
                ? "expired"
                : kind === "consume"
                  ? "consumed"
                  : "unknown_outcome",
        expires: kind === "arm" ? s.now + 3600 : s.oneShot.expires,
        gridEpoch: s.oneShot.gridEpoch,
      };
    }
    this.feed.accept(next);
    return {
      request_id: this.requestId(),
      status: "accepted_fake",
      revision: 0,
      persisted_revision: null,
      reason: "Прийнято симулятором; фізичної дії немає",
    };
  }
  history(
    range: Window,
    cursor: HistoryCursor | null = null,
    limit = 128,
  ): HistoryPage {
    if (
      !Number.isInteger(limit) ||
      limit < 1 ||
      limit > 256 ||
      range.start >= range.end ||
      !Number.isFinite(range.start) ||
      !Number.isFinite(range.end)
    )
      throw Error("Некоректний запит історії");
    const watermark = actual.length;
    const scope = `${range.start}:${range.end}`;
    if (
      cursor &&
      (cursor.scope !== scope ||
        cursor.watermark !== watermark ||
        cursor.offset < 0 ||
        !Number.isInteger(cursor.offset))
    )
      throw Error("Курсор іншого періоду");
    const rows =
      this.scenario === "empty"
        ? []
        : actual.filter((p) => p.at >= range.start && p.at < range.end);
    const start = cursor?.offset ?? 0;
    if (start > rows.length) throw Error("Курсор поза архівом");
    const page = rows.slice(start, start + limit);
    return {
      rows: structuredClone(page),
      cursor:
        start + page.length < rows.length
          ? { offset: start + page.length, scope, watermark }
          : null,
      watermark,
    };
  }
}
