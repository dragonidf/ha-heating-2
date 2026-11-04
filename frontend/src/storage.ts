import type { Persisted, Settings } from "./types";
import { defaults } from "./fixtures";
import { persisted } from "./contracts";
export type Commit = { state: Persisted; conflict: boolean };
export interface SettingsStore {
  read(): Promise<Persisted>;
  commit(
    expected: number,
    request: string,
    values: Settings,
    guard: () => boolean,
  ): Promise<Commit>;
}
export class BrowserStore implements SettingsStore {
  constructor(private readonly name = "synthetic-heating-ui-v1") {}
  private open(): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const r = indexedDB.open(this.name, 1);
      r.onupgradeneeded = () => r.result.createObjectStore("settings");
      r.onerror = () => reject(Error("Локальне сховище недоступне"));
      r.onblocked = () => reject(Error("Локальне сховище заблоковано"));
      r.onsuccess = () => resolve(r.result);
    });
  }
  private async transaction(
    write: boolean,
    change?: (current: Persisted) => Commit,
  ): Promise<Commit> {
    const db = await this.open();
    return new Promise((resolve, reject) => {
      const tx = db.transaction("settings", write ? "readwrite" : "readonly");
      const store = tx.objectStore("settings");
      let result: Commit | undefined;
      const req = store.get("config");
      req.onsuccess = () => {
        try {
          const current =
            req.result === undefined
              ? {
                  revision: 1,
                  values: structuredClone(defaults),
                  lastRequest: null,
                }
              : persisted(req.result);
          result = change
            ? change(current)
            : { state: current, conflict: false };
          if (write && !result.conflict) store.put(result.state, "config");
        } catch {
          tx.abort();
        }
      };
      tx.oncomplete = () => {
        db.close();
        if (result) resolve(structuredClone(result));
        else reject(Error("Немає підтвердження запису"));
      };
      tx.onabort = tx.onerror = () => {
        db.close();
        reject(Error("Транзакцію симуляції не завершено"));
      };
    });
  }
  async read(): Promise<Persisted> {
    return (await this.transaction(false)).state;
  }
  async commit(
    expected: number,
    request: string,
    values: Settings,
    guard: () => boolean,
  ): Promise<Commit> {
    return this.transaction(true, (current) => {
      if (!guard()) throw Error("Доступ або свіжість втрачено");
      if (current.lastRequest === request)
        return {
          state: current,
          conflict: JSON.stringify(current.values) !== JSON.stringify(values),
        };
      if (current.revision !== expected)
        return { state: current, conflict: true };
      return {
        state: persisted({
          revision: current.revision + 1,
          values,
          lastRequest: request,
        }),
        conflict: false,
      };
    });
  }
}
