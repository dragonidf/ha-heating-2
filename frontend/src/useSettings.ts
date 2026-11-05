import { useCallback, useEffect, useRef, useState } from "react";
import type { Persisted, Settings } from "./types";
import type { OperatorAPI } from "./operator";
import { defaults } from "./fixtures";
import {
  equal,
  merge,
  replaceField,
  type FieldDifference,
} from "./settingsMerge";
export function useSettings(api: OperatorAPI) {
  const [saved, setSaved] = useState<Persisted | null>(null),
    [draft, setDraft] = useState<Settings>({ ...defaults });
  const [pending, setPending] = useState(false),
    [message, setMessage] = useState(""),
    [conflict, setConflict] = useState<Persisted | null>(null),
    [error, setError] = useState(false);
  const [collisions, setCollisions] = useState<FieldDifference[]>([]);
  const previous = useRef<{ base: Settings; draft: Settings } | null>(null),
    active = useRef("");
  const current = useRef({ saved, draft });
  current.current = { saved, draft };
  const loadVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++loadVersion.current;
    try {
      const value = await api.settings();
      if (version !== loadVersion.current) return null;
      const state = current.current;
      if (state.saved && value.revision < state.saved.revision) return null;
      if (state.saved && !equal(state.draft, state.saved.values)) {
        if (value.revision !== state.saved.revision) setConflict(value);
        setMessage(
          "Стан прочитано. Незбережену чернетку збережено для порівняння.",
        );
      } else {
        setSaved(value);
        setDraft(value.values);
        setConflict(null);
        setCollisions([]);
        setMessage("");
      }
      setError(false);
      return value;
    } catch {
      if (version !== loadVersion.current) return null;
      setError(true);
      setMessage("Локальне сховище недоступне. Нічого не збережено.");
      return null;
    }
  }, [api]);
  useEffect(() => {
    void load();
  }, [load]);
  const edit = (next: Settings) => {
    previous.current = { base: saved?.values ?? defaults, draft };
    setDraft(next);
    setCollisions((fields) =>
      fields.map((f) => ({
        ...f,
        local: f.path.reduce<unknown>(
          (value, key) =>
            value && typeof value === "object"
              ? (value as Record<string, unknown>)[key]
              : undefined,
          next,
        ),
      })),
    );
    setMessage("Є незбережені зміни");
  };
  const cancel = () => {
    previous.current = { base: saved?.values ?? defaults, draft };
    if (conflict) setSaved(conflict);
    if (conflict || saved) setDraft((conflict ?? saved)!.values);
    setMessage("Чернетку скасовано");
    setConflict(null);
    setCollisions([]);
  };
  const undo = () => {
    if (previous.current) {
      const p = { base: saved?.values ?? defaults, draft };
      const restored = merge(
        previous.current.base,
        previous.current.draft,
        saved?.values ?? defaults,
      );
      setDraft(restored.value);
      setCollisions(restored.collisions);
      previous.current = p;
      setMessage("Повернуто попередню чернетку");
    }
  };
  const save = async (values = draft) => {
    if (!saved || pending || conflict || collisions.length) return;
    if (!equal(values, draft)) {
      if (!equal(draft, saved.values)) {
        setMessage(
          "Спочатку збережіть або скасуйте незбережену чернетку в налаштуваннях.",
        );
        return;
      }
      previous.current = { base: saved.values, draft };
      setDraft(values); // A rejected quick intent must remain available for merge/retry.
    }
    const id = api.requestId(),
      generation = api.feed.value.generation;
    active.current = id;
    setPending(true);
    setMessage("Записуємо й перевіряємо…");
    try {
      const r = await api.save(id, saved.revision, values, api.session);
      if (active.current !== r.request_id) {
        setMessage("Непідтверджений запит. Старе підтвердження відкинуто.");
        return;
      }
      if (generation !== api.feed.value.generation) {
        setMessage(
          "Зв’язок змінився. Старе підтвердження відкинуто; перечитайте стан.",
        );
        return;
      }
      if (r.status === "saved") {
        const state = await api.settings();
        if (
          r.persisted_revision !== r.revision ||
          state.revision !== r.revision ||
          r.revision !== saved.revision + 1 ||
          !equal(state.values, values) ||
          !api.canChange() ||
          generation !== api.feed.value.generation
        ) {
          throw Error("Підтвердження іншої версії або сесії");
        }
        setSaved(state);
        setDraft(state.values);
        setConflict(null);
        setCollisions([]);
        setMessage(r.reason);
      } else if (r.status === "conflict") {
        setConflict(await api.settings());
        setMessage(r.reason);
      } else setMessage(r.reason);
    } catch {
      setMessage(
        "Підтвердження не перевірено. Чернетку збережено; перечитайте стан.",
      );
    } finally {
      setPending(false);
    }
  };

  const rebase = () => {
    if (conflict) {
      const combined = merge(saved!.values, draft, conflict.values);
      setDraft(combined.value);
      setCollisions(combined.collisions);
      setSaved(conflict);
      setConflict(null);
      setMessage("Нова версія прочитана. Перевірте чернетку й збережіть явно.");
    }
  };
  const resolve = (path: string[], choice: "local" | "remote") => {
    const field = collisions.find((f) => equal(f.path, path));
    if (!field) return;
    if (choice === "remote") setDraft(replaceField(draft, path, field.remote));
    setCollisions(collisions.filter((f) => !equal(f.path, path)));
  };
  return {
    saved,
    draft,
    edit,
    cancel,
    undo,
    save,
    pending,
    message,
    conflict,
    rebase,
    error,
    load,
    collisions,
    resolve,
    differences:
      saved && conflict
        ? merge(saved.values, draft, conflict.values).fields
        : [],
    dirtyPaths: saved
      ? merge(saved.values, draft, saved.values)
          .fields.filter((f) => !equal(f.base, f.local))
          .map((f) => f.path)
      : [],
  };
}
export type SettingsController = ReturnType<typeof useSettings>;
