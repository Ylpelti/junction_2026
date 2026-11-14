import type { DataSource } from "../lib/types";

type Props = {
  view: "nurse" | "doctor";
  onView: (v: "nurse" | "doctor") => void;
  useCS: boolean;
  onToggleCS: () => void;
  source: DataSource;
  onSource?: (s: DataSource) => void;
  onReset: () => void;
};

function Pill({ on, label, onClick, title }: { on: boolean; label: string; onClick: () => void; title?: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      title={title}
      className={`min-h-11 cursor-pointer rounded-lg border px-3 py-1.5 text-[13px] font-semibold ${
        on ? "border-[#F3F4F6] bg-[#F3F4F6] text-ink" : "border-bar-line bg-transparent text-[#E5E7EB]"
      }`}
    >
      {label}
    </button>
  );
}

export function DemoBar({ view, onView, useCS, onToggleCS, source, onSource, onReset }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-3 bg-bar px-6 py-2.5 text-[#E5E7EB]" role="region" aria-label="Demo controls">
      <span className="text-xs font-bold tracking-[0.08em] text-[#C4B5FD] uppercase">Demo controls</span>
      <span className="text-[12.5px] text-[#C9CED6]">
        Not part of the product · all patients are synthetic · compare today&apos;s practice with CancerSignal
      </span>
      <div className="ml-auto flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={onReset}
          title="Resets the screen only. Notes already saved to the backend stay in its database."
          className="min-h-11 cursor-pointer rounded-lg border border-[#F87171] bg-transparent px-3 py-1.5 text-[13px] font-semibold text-[#FCA5A5]"
        >
          Reset demo
        </button>
        <Pill on={view === "nurse"} label="Nurse view" onClick={() => onView("nurse")} />
        <Pill on={view === "doctor"} label="Physician view" onClick={() => onView("doctor")} />
        {onSource && (
          <>
            <Pill on={source === "backend"} label="Backend data" onClick={() => onSource("backend")} title="Patients and analysis from the FastAPI backend" />
            <Pill
              on={source === "prototype"}
              label="Prototype data"
              onClick={() => onSource("prototype")}
              title="Canned patients and results from the design prototype; no backend calls"
            />
          </>
        )}
        <button
          type="button"
          onClick={onToggleCS}
          aria-pressed={useCS}
          className="flex min-h-11 cursor-pointer items-center gap-2.5 rounded-full border border-bar-line bg-transparent py-1 pr-3 pl-1.5 text-[13px] text-[#F3F4F6]"
        >
          <span className={`box-border flex h-5 w-9 items-center rounded-full p-0.5 ${useCS ? "bg-[#7C3AED]" : "bg-mute-3"}`} aria-hidden="true">
            <span className={`h-4 w-4 rounded-full bg-white transition-[margin] ${useCS ? "ml-4" : "ml-0"}`} />
          </span>
          <span className="font-semibold">{useCS ? "With CancerSignal" : "Current practice (no CancerSignal)"}</span>
        </button>
      </div>
    </div>
  );
}
