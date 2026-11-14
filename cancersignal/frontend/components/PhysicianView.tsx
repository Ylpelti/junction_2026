import type { QueueItem, QueueLevel } from "../lib/types";

const STYLE: Record<QueueLevel, { chip: string; chipCls: string; stripe: string }> = {
  urgent: { chip: "Urgent · CancerSignal", chipCls: "bg-red-soft text-red-ink", stripe: "bg-red-main" },
  review: { chip: "CancerSignal", chipCls: "bg-amber-soft text-amber-dark", stripe: "bg-amber-edge" },
  normal: { chip: "Routine", chipCls: "bg-chip text-mute", stripe: "bg-field" },
};

const CS_ACTIONS: [string, string][] = [
  ["Order FIT (stool blood test)", "FIT ordered"],
  ["Refer to specialist care", "Referral made"],
  ["No action", "No action"],
];

type Props = { queue: QueueItem[]; decisions: Record<string, string>; onDecide: (key: string, decision: string) => void };

export function PhysicianView({ queue, decisions, onDecide }: Props) {
  const waiting = queue.filter((q) => !decisions[q.key]).length;
  return (
    <>
      <header className="flex flex-wrap items-center gap-4 bg-header px-6 py-2.5 text-white">
        <span className="text-[15px] font-bold tracking-[0.01em]">Health Centre · Patient Record System</span>
        <span className="text-[12.5px] text-[#D1D5DB]">(fictional demo)</span>
        <span className="ml-auto text-[13px] text-[#E5E7EB]">Dr M. Salo · Physician on duty</span>
      </header>
      <main className="box-border flex w-full max-w-[1100px] flex-col gap-3.5 px-6 py-5">
        <div className="flex flex-wrap items-baseline gap-3.5">
          <h1 className="m-0 text-xl font-bold">Consultation queue</h1>
          <span className="text-[13.5px] text-mute">{waiting} waiting · sorted by urgency</span>
        </div>
        <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
          {queue.map((q) => {
            const st = STYLE[q.level];
            const decision = decisions[q.key];
            const actions = q.cs ? CS_ACTIONS : ([["Acknowledge", "Acknowledged"]] as [string, string][]);
            return (
              <li key={q.key} className="flex overflow-hidden rounded-xl border border-line bg-white">
                <span className={`w-1.5 shrink-0 ${st.stripe}`} aria-hidden="true" />
                <div className="flex min-w-0 flex-1 flex-col gap-2 px-4 py-3.5">
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className={`rounded-full px-2.5 py-[3px] text-xs font-bold ${st.chipCls}`}>{st.chip}</span>
                    <span className="text-[15px] font-bold">{q.name}</span>
                    <span className="text-[13px] text-mute">{q.demo}</span>
                    <span className="ml-auto text-[12.5px] text-mute-2">
                      Received {q.time} · {q.from}
                    </span>
                  </div>
                  <span className="text-sm leading-normal text-ink-2">{q.summary}</span>
                  {q.cs && q.findings.length > 0 && (
                    <div className="flex flex-col gap-1.5 border-t border-line-2 pt-2">
                      {q.findings.map((f) => (
                        <div key={f.id} className="flex flex-wrap items-baseline gap-x-2.5 gap-y-1.5">
                          <span className="rounded-md bg-badge-bg px-2 py-0.5 text-[11.5px] font-bold text-badge-fg">{f.id}</span>
                          <span className="text-[13.5px] font-semibold">{f.title}</span>
                          <span className="text-[12.5px] text-mute-2">
                            Rule {f.rule}
                            {f.ruleSrc && ` · ${f.ruleSrc}`}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  {decision ? (
                    <span className="text-[13.5px] font-semibold text-ok">Decided: {decision}</span>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      {actions.map(([label, result]) => (
                        <button
                          key={label}
                          type="button"
                          onClick={() => onDecide(q.key, result)}
                          className="min-h-11 cursor-pointer rounded-lg border border-field bg-white px-3.5 py-2 text-[13.5px] font-semibold text-ink"
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
        <p className="m-0 text-[12.5px] text-mute-2">CancerSignal sets the order only. The physician makes every decision.</p>
      </main>
    </>
  );
}
