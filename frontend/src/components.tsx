import { useId, useRef } from "react";
import type { ReactNode } from "react";
export function Icon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    home: "M3 10 12 3l9 7v11h-6v-7H9v7H3Z",
    history: "M3 12a9 9 0 1 0 3-6M3 3v5h5M12 7v5l3 2",
    settings: "M4 7h16M7 3v8M4 17h16M16 13v8",
    fire: "M13 2c2 6-3 6-1 10 2-1 3-2 3-4 5 6 4 13-3 14-7-1-10-8-5-14 0 4 3 4 3 1 0-2 2-3 3-7Z",
    sun: "M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1 1M18 18l1 1M5 19l1-1M18 6l1-1",
    arrow: "M5 12h14M13 6l6 6-6 6",
    check: "m5 12 4 4L19 6",
    info: "M12 11v6M12 7v1M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20",
    moon: "M20 15A8 8 0 0 1 9 4a8 8 0 1 0 11 11",
    fan: "M12 12C4 8 7 1 12 4v8c4-8 11-5 8 0h-8c8 4 5 11 0 8v-8c-4 8-11 5-8 0h8Z",
  };
  return (
    <svg
      viewBox="0 0 24 24"
      width="22"
      height="22"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={paths[name] ?? paths.info} />
    </svg>
  );
}
export function Card({
  title,
  children,
  aside,
  className = "",
}: {
  title: string;
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      <div className="section-title">
        <h2>{title}</h2>
        {aside}
      </div>
      {children}
    </section>
  );
}
export function Badge({
  children,
  tone = "muted",
}: {
  children: ReactNode;
  tone?: string;
}) {
  return <span className={`badge ${tone}`}>{children}</span>;
}
export function Dialog({
  title,
  trigger,
  children,
}: {
  title: string;
  trigger: string;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const id = useId();
  return (
    <>
      <button className="text-button" onClick={() => ref.current?.showModal()}>
        {trigger}
        <Icon name="arrow" />
      </button>
      <dialog ref={ref} aria-labelledby={id}>
        <div className="section-title">
          <h2 id={id}>{title}</h2>
          <button
            aria-label="Закрити деталі"
            onClick={() => ref.current?.close()}
          >
            ×
          </button>
        </div>
        {children}
        <button className="primary" onClick={() => ref.current?.close()}>
          Готово
        </button>
      </dialog>
    </>
  );
}
export { Chart } from "./Chart";
