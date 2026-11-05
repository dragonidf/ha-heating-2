import { equal } from "./settingsMerge";
import { withDeadline } from "./domain";
import { SnapshotFeed } from "./mock";
import { persisted, readReceipt, object } from "./contracts";
import {
  readSnapshot,
  readOverview,
  readPage,
  readEnergy,
  readModel,
  validSettings,
} from "./nativeContracts";
import {
  emptyView,
  type Control,
  type ModelAction,
  type OperatorAPI,
  type OperatorView,
} from "./operator";
import type {
  APIReceipt,
  EnergyInterval,
  HistoryCursor,
  HistoryPage,
  Settings,
  Snapshot,
  Window,
} from "./types";
export interface HassConnection {
  subscribeMessage<T>(
    callback: (message: T) => void,
    message: Record<string, unknown>,
    options?: { resubscribe?: boolean },
  ): Promise<() => void>;
  addEventListener?(
    event: "ready" | "disconnected",
    callback: () => void,
  ): void;
  removeEventListener?(
    event: "ready" | "disconnected",
    callback: () => void,
  ): void;
}
export interface Hass {
  callWS<T>(message: Record<string, unknown>): Promise<T>;
  connection: HassConnection;
  connected?: boolean;
  user?: { id: string; is_admin: boolean };
  themes?: { darkMode: boolean };
}
function release(unsubscribe?: () => void) {
  if (!unsubscribe) return;
  try {
    void Promise.resolve(unsubscribe()).catch(() => {});
  } catch {
    /* Detached HA subscription is already unusable. */
  }
}
function emptySnapshot(): Snapshot {
  return {
    version: 1,
    seq: 0,
    generation: 0,
    now: 0,
    connected: false,
    permitted: false,
    status: {
      status_seq: 0,
      boot_id: "pending",
      owner_epoch: 0,
      actual: null,
      desired: "stop_demand",
      mode: "SAFE_HOLD",
      snapshot_id: "pending",
      snapshot_at: 0,
      archive_pending: 0,
      archive_lost: 0,
      receipt_stage: null,
      physical_verified: false,
    },
    room: { value: null, observed: 0, quality: "missing" },
    grid: null,
    notices: [],
    fan: {
      phase: "unknown",
      requested: null,
      actual: null,
      night: false,
      fire: false,
    },
    oneShot: { state: "inactive", expires: null, gridEpoch: 0 },
    diagnostics: {
      loopLagMs: null,
      persistence: "pending",
      worker: "pending",
      source: "missing",
    },
  };
}
export class NativeAPI implements OperatorAPI {
  readonly native = true;
  readonly session = Object.freeze({ native: true });
  readonly feed = new SnapshotFeed(emptySnapshot());
  readonly scenario = undefined;
  model = { revision: 0, candidate: false, frozen: true };
  view?: OperatorView;
  private enabled: boolean | undefined;
  private errors = new Map<string, string>();
  get dataErrors() {
    return [...this.errors.values()];
  }
  private historyRequest = 0;
  private intervals: readonly EnergyInterval[] | null = null;
  private archive: {
    range: Window;
    rows: HistoryPage["rows"];
    watermark: number;
  } | null = null;
  private archiveError = false;
  private unsubscribe?: () => void;
  private epoch = 0;
  private closed = false;
  private browserOnline =
    typeof navigator === "undefined" || navigator.onLine !== false;
  private refreshing?: Promise<void>;
  constructor(
    private hass: Hass,
    private readonly entryId: string,
  ) {
    if (!/^[a-zA-Z0-9_-]{1,128}$/.test(entryId))
      throw Error("Некоректний entry_id");
    hass.connection.addEventListener?.("disconnected", this.offline);
    hass.connection.addEventListener?.("ready", this.ready);
    if (typeof window !== "undefined") {
      window.addEventListener("offline", this.browserOffline);
      window.addEventListener("online", this.browserReady);
    }
  }
  private message(operation: string, values: Record<string, unknown> = {}) {
    return {
      type: `heating_ai/${operation}`,
      entry_id: this.entryId,
      version: [2, 0],
      ...values,
    };
  }
  private async read(operation: string, values: Record<string, unknown> = {}) {
    if (!this.browserOnline || this.closed)
      throw Error("Немає зв’язку. Лише читання.");
    const epoch = this.epoch;
    const result = await withDeadline(
      this.hass.callWS<unknown>(this.message(operation, values)),
    );
    if (epoch !== this.epoch || !this.browserOnline || this.closed)
      throw Error("Сесію змінено. Перечитайте стан.");
    return result;
  }
  private browserOffline = () => {
    this.browserOnline = false;
    this.offline();
  };
  private browserReady = () => {
    this.browserOnline = true;
    this.ready();
  };
  private offline = () => {
    this.epoch++;
    release(this.unsubscribe);
    this.unsubscribe = undefined;
    this.feed.reset({ ...this.feed.value, connected: false, permitted: false });
  };
  private ready = () => {
    if (this.closed || !this.browserOnline) return;
    if (this.refreshing) {
      void this.refreshing.then(
        () => {
          if (!this.feed.value.connected) this.ready();
        },
        () => {},
      );
      return;
    }
    void this.reconnect().catch(this.offline);
  };
  updateConnection(connected: boolean, hass = this.hass) {
    this.hass = hass;
    if (!connected && this.feed.value.connected) this.offline();
  }
  async start() {
    await this.reconnect();
  }
  reconnect(): Promise<void> {
    if (this.closed) return Promise.reject(Error("Панель закрита"));
    if (!this.browserOnline)
      return Promise.reject(Error("Немає зв’язку. Лише читання."));
    if (this.refreshing) return this.refreshing;
    this.refreshing = this.bootstrap().finally(() => {
      this.refreshing = undefined;
    });
    return this.refreshing;
  }
  private async bootstrap() {
    const epoch = ++this.epoch;
    release(this.unsubscribe);
    this.unsubscribe = undefined;
    this.feed.reset({ ...this.feed.value, connected: false, permitted: false });
    try {
      const [status, overview] = await Promise.allSettled([
        this.read("status"),
        this.read("overview"),
        this.settings(),
      ]);
      if (this.closed || epoch !== this.epoch) return;
      if (status.status !== "fulfilled") throw status.reason;
      const state = readSnapshot(status.value);
      this.errors.clear();
      this.view = emptyView(state.now);
      this.model = { revision: 0, candidate: false, frozen: true };
      this.enabled = undefined;
      try {
        if (overview.status !== "fulfilled") throw overview.reason;
        const view = readOverview(overview.value);
        this.view = view;
        this.model = view.model;
        this.enabled = view.enabled;
      } catch {
        this.errors.set(
          "overview",
          "Синтетичний огляд недоступний. Прогноз, модель і підсумок невідомі.",
        );
      }
      this.archive = null;
      this.intervals = null;
      // The HA session owns transport; a full authoritative snapshot replaces stale cached state.
      this.feed.reset(state);
      const range = { start: state.now - 7 * 86400, end: state.now + 1 };
      await Promise.allSettled([this.loadHistory(range), this.refreshEnergy()]);
      if (this.closed || epoch !== this.epoch) return;
      const pendingSubscription =
        this.hass.connection.subscribeMessage<unknown>(
          (raw) => {
            if (epoch === this.epoch && !this.closed) this.event(raw);
          },
          this.message("subscribe"),
          { resubscribe: false },
        );
      // A late subscription still needs disposal after a timeout/unmount.
      let disposed = false;
      const dispose = (unsubscribe: () => void) => {
        if (!disposed) {
          disposed = true;
          release(unsubscribe);
        }
      };
      void pendingSubscription.then(
        (unsubscribe) => {
          if (this.closed || epoch !== this.epoch) dispose(unsubscribe);
        },
        () => {},
      );
      const unsubscribe = await withDeadline(pendingSubscription);
      if (this.closed || epoch !== this.epoch) dispose(unsubscribe);
      else this.unsubscribe = () => dispose(unsubscribe);
    } catch (error) {
      if (epoch === this.epoch) this.offline();
      throw error;
    }
  }
  private event = (raw: unknown) => {
    try {
      const next = readSnapshot(raw),
        old = this.feed.value;
      if (
        next.status.boot_id !== old.status.boot_id ||
        next.generation !== old.generation
      ) {
        this.offline();
        this.ready();
        return;
      }
      if (next.seq === old.seq) {
        this.feed.reset(next);
        return;
      }
      if (!this.feed.accept(next) && next.seq > old.seq) this.ready();
    } catch {
      this.offline();
    }
  };
  close() {
    this.closed = true;
    this.epoch++;
    release(this.unsubscribe);
    this.hass.connection.removeEventListener?.("disconnected", this.offline);
    this.hass.connection.removeEventListener?.("ready", this.ready);
    if (typeof window !== "undefined") {
      window.removeEventListener("offline", this.browserOffline);
      window.removeEventListener("online", this.browserReady);
    }
  }
  canChange() {
    const s = this.feed.value;
    return (
      !this.closed &&
      this.browserOnline &&
      this.enabled !== false &&
      s.connected &&
      s.permitted &&
      s.room.quality === "valid" &&
      s.now >= s.room.observed &&
      !["SAFE_HOLD", "RECOVERING"].includes(s.status.mode)
    );
  }
  canStop() {
    return (
      !this.closed &&
      this.browserOnline &&
      this.enabled !== false &&
      this.hass.connected !== false &&
      this.hass.user?.is_admin === true &&
      this.feed.value.connected &&
      this.feed.value.status.boot_id !== "pending"
    );
  }
  requestId() {
    return `native.ui.${crypto.randomUUID()}`;
  }
  async settings() {
    return persisted(await this.read("settings/get"));
  }
  private async mutate(
    operation: string,
    values: Record<string, unknown>,
    session: object,
  ) {
    const stopping = operation === "control" && values.kind === "pause";
    if (
      session !== this.session ||
      !(stopping ? this.canStop() : this.canChange())
    )
      throw Error("Лише читання. Симуляція або доступ недоступні.");
    const s = this.feed.value,
      epoch = this.epoch;
    const result = await this.read(operation, {
      ...values,
      boot_id: s.status.boot_id,
      generation: s.generation,
      owner_epoch: s.status.owner_epoch,
    });
    if (
      epoch !== this.epoch ||
      this.feed.value.status.boot_id !== s.status.boot_id ||
      this.feed.value.generation !== s.generation ||
      !(stopping ? this.canStop() : this.feed.value.permitted)
    )
      throw Error("Сесію змінено. Перечитайте стан.");
    return result;
  }
  async save(
    id: string,
    expected: number,
    values: Settings,
    session: object,
  ): Promise<APIReceipt> {
    if (
      !id ||
      id.length > 128 ||
      !Number.isSafeInteger(expected) ||
      expected < 1 ||
      !validSettings(values)
    )
      throw Error("Некоректні налаштування");
    const receipt = readReceipt({
      version: [2, 0],
      type: "APIReceipt",
      data: await this.mutate(
        "settings/save",
        { request_id: id, expected_revision: expected, values },
        session,
      ),
    });
    if (receipt.request_id !== id) throw Error("Підтвердження іншого запиту");
    if (receipt.status === "saved") {
      const readback = await this.settings();
      if (
        !this.canChange() ||
        readback.revision !== receipt.persisted_revision ||
        receipt.revision !== receipt.persisted_revision ||
        readback.lastRequest !== id ||
        !equal(readback.values, values)
      )
        throw Error("Читання записаного стану не підтверджене");
    }
    return receipt;
  }
  async control(kind: Control, session: object) {
    if (
      ![
        "pause",
        "resume",
        "arm",
        "cancel",
        "expire",
        "unknown",
        "consume",
      ].includes(kind)
    )
      throw Error("Некоректна дія");
    const id = this.requestId();
    const receipt = readReceipt({
      version: [2, 0],
      type: "APIReceipt",
      data: await this.mutate("control", { kind, request_id: id }, session),
    });
    if (receipt.request_id !== id) throw Error("Підтвердження іншого запиту");
    return receipt;
  }
  async modelAction(kind: ModelAction, session: object) {
    if (!["train", "promote", "rollback", "freeze"].includes(kind))
      throw Error("Некоректна дія");
    const result = object(
      await this.mutate(
        "model",
        { kind, request_id: this.requestId() },
        session,
      ),
    );
    if (typeof result.reason !== "string") throw Error("Некоректна відповідь");
    this.model = readModel(result.model);
    this.feed.reset({ ...this.feed.value });
    return result.reason;
  }
  async loadHistory(range: Window) {
    if (
      ![range.start, range.end].every(Number.isFinite) ||
      range.start >= range.end ||
      range.end - range.start > 32 * 86400
    )
      throw Error("Некоректний період");
    const epoch = this.epoch,
      request = ++this.historyRequest;
    let cursor: HistoryCursor | null = null,
      watermark: number | undefined;
    const rows: import("./types").Point[] = [];
    try {
      do {
        const page = readPage(
          await this.read("history", { ...range, cursor, limit: 128 }),
        );
        if (epoch !== this.epoch || this.closed) throw Error("Сесію змінено");
        if (request !== this.historyRequest) return;
        if (watermark !== undefined && watermark !== page.watermark)
          throw Error("Архів змінився");
        watermark = page.watermark;
        for (const point of page.rows) {
          if (
            point.at < range.start ||
            point.at >= range.end ||
            (rows.length && point.at <= rows.at(-1)!.at) ||
            rows.length >= 100000
          )
            throw Error("Некоректний архів");
          rows.push(point);
        }
        if (
          page.cursor &&
          (page.cursor.offset !== rows.length ||
            page.cursor.scope !== `${range.start}:${range.end}` ||
            !page.rows.length)
        )
          throw Error("Курсор не просувається");
        cursor = page.cursor;
      } while (cursor);
      this.archive = { range: { ...range }, rows, watermark: watermark! };
      this.archiveError = false;
      this.errors.delete("history");
      if (
        this.view &&
        range.start <= this.feed.value.now - 6 * 3600 &&
        range.end >= this.feed.value.now
      )
        this.view = {
          ...this.view,
          actual: rows.filter((p) => p.at <= this.feed.value.now),
        };
      this.feed.reset({ ...this.feed.value });
    } catch (error) {
      if (epoch === this.epoch && request === this.historyRequest) {
        this.archiveError = true;
        this.errors.set(
          "history",
          "Температурний архів недоступний. Виміри та покриття невідомі.",
        );
        this.feed.reset({ ...this.feed.value });
      }
      throw error;
    }
  }
  history(
    range: Window,
    cursor: HistoryCursor | null = null,
    limit = 128,
  ): HistoryPage {
    if (
      ![range.start, range.end].every(Number.isFinite) ||
      range.start >= range.end ||
      !Number.isInteger(limit) ||
      limit < 1 ||
      limit > 256 ||
      !this.archive ||
      this.archiveError ||
      range.start < this.archive.range.start ||
      range.end > this.archive.range.end
    )
      throw Error("Архів не прочитаний для цього періоду");
    const scope = `${range.start}:${range.end}`,
      watermark = this.archive.watermark;
    if (
      cursor &&
      (cursor.scope !== scope ||
        cursor.watermark !== watermark ||
        !Number.isSafeInteger(cursor.offset) ||
        cursor.offset < 0)
    )
      throw Error("Некоректний курсор");
    const rows = this.archive.rows.filter(
        (p) => p.at >= range.start && p.at < range.end,
      ),
      start = cursor?.offset ?? 0;
    if (start > rows.length) throw Error("Курсор поза архівом");
    return {
      rows: rows.slice(start, start + limit),
      watermark,
      cursor:
        start + limit < rows.length
          ? { offset: start + limit, scope, watermark }
          : null,
    };
  }
  private async refreshEnergy() {
    const epoch = this.epoch;
    try {
      const intervals = readEnergy(await this.read("energy"));
      if (epoch !== this.epoch || this.closed) return;
      this.intervals = intervals;
      this.errors.delete("energy");
    } catch {
      if (epoch !== this.epoch || this.closed) return;
      this.errors.set(
        "energy",
        "Архів енергії недоступний. Енергія та вартість невідомі.",
      );
    }
    this.feed.reset({ ...this.feed.value });
  }
  energyHistory() {
    if (!this.intervals) throw Error("Архів енергії недоступний");
    return this.intervals;
  }
}
