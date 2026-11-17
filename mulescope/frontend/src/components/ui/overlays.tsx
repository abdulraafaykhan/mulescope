/**
 * Overlays: a side drawer and a modal dialog. Both close on Escape, trap the
 * initial focus and return it on close.
 */
import { useEffect, useRef, type ReactNode, type RefObject } from "react";
import { X } from "lucide-react";

function useEscape(open: boolean, onClose: () => void) {
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);
}

function useFocusReturn(open: boolean, ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    if (!open) return;
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.focus();
    return () => previous?.focus();
  }, [open, ref]);
}

export function Drawer({ open, onClose, title, width = 520, children }: { open: boolean; onClose: () => void; title: ReactNode; width?: number; children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEscape(open, onClose);
  useFocusReturn(open, ref);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="presentation">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" className="relative flex h-full flex-col border-l border-line bg-panel shadow-2xl outline-none" style={{ width }}>
        <header className="flex h-12 shrink-0 items-center justify-between border-b border-line px-4">
          <div className="text-base font-semibold">{title}</div>
          <button type="button" onClick={onClose} className="rounded p-1 text-secondary hover:bg-elevated" aria-label="Close drawer">
            <X size={16} />
          </button>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}

export function Dialog({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: ReactNode; children: ReactNode; footer: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEscape(open, onClose);
  useFocusReturn(open, ref);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="presentation">
      <div className="absolute inset-0 bg-black/60" onClick={onClose} aria-hidden />
      <div ref={ref} tabIndex={-1} role="dialog" aria-modal="true" className="relative w-[560px] max-w-[92vw] rounded-[8px] border border-line bg-panel shadow-2xl outline-none">
        <header className="flex h-11 items-center justify-between border-b border-line px-4">
          <div className="text-base font-semibold">{title}</div>
          <button type="button" onClick={onClose} className="rounded p-1 text-secondary hover:bg-elevated" aria-label="Close dialog">
            <X size={16} />
          </button>
        </header>
        <div className="max-h-[70vh] overflow-y-auto p-4">{children}</div>
        <footer className="flex justify-end gap-2 border-t border-line px-4 py-3">{footer}</footer>
      </div>
    </div>
  );
}

export function Tabs<T extends string>({ tabs, value, onChange, right }: { tabs: { id: T; label: ReactNode }[]; value: T; onChange: (id: T) => void; right?: ReactNode }) {
  return (
    <div className="flex h-10 items-center justify-between border-b border-line px-2" role="tablist">
      <div className="flex h-full items-center">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={value === t.id}
            onClick={() => onChange(t.id)}
            className={`flex h-full items-center gap-1.5 border-b-2 px-3 text-sm transition ${value === t.id ? "border-accent text-primary" : "border-transparent text-secondary hover:text-primary"}`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {right}
    </div>
  );
}
