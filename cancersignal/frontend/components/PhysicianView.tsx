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

/**
 * Why CancerSignal flagged this patient. Everything shown comes from the analysis
 * (rule priority, rule sources, evidence records); the UI does not judge urgency.
 */
function Reasons({ item }: { item: QueueItem }) {
  const urgentRules = item.findings.filter((f) => f.priority === "urgent").map((f) => f.rule);
  return (
    <section aria-label={`Reasons for the CancerSignal alert for ${item.name}`} className="flex flex-col gap-2.5 border-t border-line-2 pt-2.5">
      <h3 className="m-0 text-[12.5px] font-semibold tracking-[0.06em] text-mute-2 uppercase">Why CancerSignal flagged this</h3>
      {item.level === "urgent" && urgentRules.length > 0 && (
        <p className="m-0 rounded-lg border border-red-line bg-red-soft px-3 py-2 text-[13.5px] leading-[1.45] text-red-ink">
          <strong>Urgent</strong> because {urgentRules.length === 1 ? "this rule is" : "these rules are"} marked urgent in the rulebook:{" "}
          {urgentRules.join(", ")}.
        </p>
      )}
      {item.findings.map((f) => (
        <div key={f.id} className="flex flex-col gap-1.5 rounded-[10px] border border-line-2 px-3.5 py-2.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-badge-bg px-2 py-0.5 text-[11.5px] font-bold text-badge-fg">{f.id}</span>
            <span className="text-[14px] font-semibold">{f.title}</span>
            <span
              className={`ml-auto rounded-md border px-2 py-0.5 text-[11.5px] font-bold uppercase ${
                f.priority === "urgent" ? "border-red-line bg-red-soft text-red-ink" : "border-line-3 bg-amber-soft text-amber-dark"
              }`}
            >
              {f.priority === "urgent" ? "Urgent" : "Review"}
            </span>
          </div>
          {f.detail && <p className="m-0 text-[13.5px] leading-[1.45] text-mute">{f.detail}</p>}
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="text-xs text-mute-2">Sources:</span>
            {f.sources.length === 0 && <span className="text-xs text-mute-2">none verifiable</span>}
            {f.sources.map((s) => (
              <span key={s.id} className="rounded-md bg-chip px-[7px] py-0.5 text-xs font-semibold text-mute">
                {s.label}
              </span>
            ))}
          </div>
          <span className="text-xs text-mute-2">
            Rule <strong className="text-ink">{f.rule}</strong>
            {f.ruleSrc && ` · ${f.ruleSrc}`}
          </span>
        </div>
      ))}
      {item.missing.length > 0 && (
        <div className="flex flex-col gap-1">
          <h4 className="m-0 text-[12px] font-semibold tracking-[0.06em] text-mute-2 uppercase">Not found in records</h4>
          <ul className="m-0 flex flex-col gap-0.5 pl-4.5">
            {item.missing.map((m, i) => (
              <li key={i} className="text-[13px] text-ink-2">
                {m}
              </li>
            ))}
          </ul>
        </div>
      )}
      <p className="m-0 text-xs text-mute-2">Decision support only. No alert does not rule out cancer.</p>
    </section>
  );
}

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
                  {q.cs && q.findings.length > 0 && <Reasons item={q} />}
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
