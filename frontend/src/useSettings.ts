import { useCallback, useEffect, useRef, useState } from "react";
import type { Persisted, Settings } from "./types";
import type { DemoAPI } from "./mock";
import { defaults } from "./fixtures";
export function useSettings(api: DemoAPI) {
  const [saved, setSaved] = useState<Persisted | null>(null),
    [draft, setDraft] = useState<Settings>({ ...defaults });
  const [pending, setPending] = useState(false),
    [message, setMessage] = useState(""),
    [conflict, setConflict] = useState<Persisted | null>(null),
    [error, setError] = useState(false);
  const previous = useRef<Settings | null>(null),
    active = useRef("");
  const load = useCallback(async () => {
    try {
      const value = await api.settings();
      setSaved(value);
      setDraft(value.values);
      setError(false);
      setMessage("");
      return value;
    } catch {
      setError(true);
      setMessage("Локальне сховище недоступне. Нічого не збережено.");
      return null;
    }
  }, [api]);
  useEffect(() => {
    void load();
  }, [load]);
  const edit = (next: Settings) => {
    previous.current = draft;
    setDraft(next);
    setMessage("Є незбережені зміни");
  };
  const cancel = () => {
    previous.current = draft;
    if (saved) setDraft(saved.values);
    setMessage("Чернетку скасовано");
    setConflict(null);
  };
  const undo = () => {
    if (previous.current) {
      const p = draft;
      setDraft(previous.current);
      previous.current = p;
      setMessage("Повернуто попередню чернетку");
    }
  };
  const save = async (values = draft) => {
    if (!saved || pending) return;
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
          JSON.stringify(state.values) !== JSON.stringify(values) ||
          !api.canChange() ||
          generation !== api.feed.value.generation
        ) {
          throw Error("Підтвердження іншої версії або сесії");
        }
        setSaved(state);
        setDraft(state.values);
        setConflict(null);
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
      setSaved(conflict);
      setConflict(null);
      setMessage("Нова версія прочитана. Перевірте чернетку й збережіть явно.");
    }
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
  };
}
export type SettingsController = ReturnType<typeof useSettings>;
