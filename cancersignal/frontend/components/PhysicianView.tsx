import { formatMeasurement } from "../lib/format";
import { displayDate } from "../lib/mappers";
import { ClinicalExplanationCard } from "./ClinicalExplanationCard";
import { type DecisionAction } from "../lib/api";
import { QCancerEstimateCard } from "./FindingsPanel";
import { AnalysisEvidence } from "./AnalysisEvidence";
import type { QueueItem, QueueLevel } from "../lib/types";

const STYLE: Record<QueueLevel, { chip: string; chipCls: string; stripe: string }> = {
  urgent: { chip: "Urgent · CancerSignal", chipCls: "bg-red-soft text-red-ink", stripe: "bg-red-main" },
  review: { chip: "CancerSignal", chipCls: "bg-amber-soft text-amber-dark", stripe: "bg-amber-edge" },
  normal: { chip: "Routine", chipCls: "bg-chip text-mute", stripe: "bg-field" },
};

const CS_ACTIONS: [string, DecisionAction][] = [
  ["Simulate FIT order (stool blood test)", "fit_ordered"],
  ["Simulate referral to specialist care", "referral_made"],
  ["No action", "no_action"],
];

type Props = {
  queue: QueueItem[];
  history?: QueueItem[];
  busy?: string;
  decisions: Record<string, string>;
  onDecide: (key: string, decision: DecisionAction) => void;
  loading?: boolean;
  notice?: string;
  onRefresh?: () => void;
};

/**
 * Why CancerSignal flagged this patient. Everything shown comes from the analysis
 * (rule priority, rule sources, evidence records); the UI does not judge urgency.
 */
function Reasons({ item }: { item: QueueItem }) {
  // Show the rule ID (e.g. "SUO-08") when the rule text starts with one.
  const urgentRules = item.findings.filter((f) => f.priority === "urgent").map((f) => f.rule.match(/^[A-Z]+-\d+/)?.[0] ?? f.rule);
  return (
    <section aria-label={`Reasons for the CancerSignal alert for ${item.name}`} className="flex flex-col gap-2.5 border-t border-line-2 pt-2.5">
      <h3 className="m-0 text-[12.5px] font-semibold tracking-[0.06em] text-mute-2 uppercase">Täyttyneet säännöt</h3>
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
          <details className="text-xs text-mute-2"><summary className="cursor-pointer">Rule provenance</summary>
            Rule <strong className="text-ink">{f.rule}</strong>
            {f.ruleSrc && ` · ${f.ruleSrc}`}
          </details>
        </div>
      ))}
      {item.missing.length > 0 && (
        <details className="flex flex-col gap-1">
          <summary className="cursor-pointer text-xs text-mute-2">Missing information and technical limitations</summary>
          <ul className="m-0 flex flex-col gap-0.5 pl-4.5">
            {item.missing.map((m, i) => (
              <li key={i} className="text-[13px] text-ink-2">
                {m}
              </li>
            ))}
          </ul>
        </details>
      )}
      <p className="m-0 text-xs text-mute-2">Decision support only. No alert does not rule out cancer.</p>
    </section>
  );
}

export function PhysicianView({ queue, history = [], busy, decisions, onDecide, loading, notice, onRefresh }: Props) {
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
          {onRefresh && (
            <button
              type="button"
              onClick={onRefresh}
              className="ml-auto min-h-11 cursor-pointer rounded-lg border border-field bg-white px-3.5 py-2 text-[13.5px] font-semibold text-ink"
            >
              Refresh queue
            </button>
          )}
        </div>
        {loading && (
          <span role="status" className="text-sm text-mute-2">
            Loading the review queue…
          </span>
        )}
        {notice && (
          <div role="alert" className="rounded-xl border border-red-line bg-red-soft px-4 py-3 text-sm text-red-ink">
            {notice}
          </div>
        )}
        <p className="text-sm text-mute">Simulation only. These actions create no real medical orders or referrals.</p>
        {!loading && !notice && queue.length === 0 && <p>No pending review requests.</p>}
        <ol className="m-0 flex list-none flex-col gap-2.5 p-0">
          {[...queue, ...history].map((q, index) => {
            const st = STYLE[q.level];
            const decision = decisions[q.key];
            const observations = q.observations ?? q.analysis?.sourceObservations ?? [];
            // Match recorded test codes/status only. Never infer a need to repeat a test.
            const isFit = (code: string | null) => ["SYNTHETIC-FIT", "F-HB-FIT", "FIT"].includes((code ?? "").toUpperCase());
            const completed = observations.filter(o => o.status === "completed" && (o.observation_type === "investigation" || (o.observation_type === "laboratory" && isFit(o.code))));
            const completedFit = completed.some(o => isFit(o.code));
            const actions = q.cs ? CS_ACTIONS : ([["Acknowledge", "acknowledged"]] as [string, DecisionAction][]);
            return (
              <li key={q.key} className="flex overflow-hidden rounded-xl border border-line bg-white">
                <span className={`w-1.5 shrink-0 ${st.stripe}`} aria-hidden="true" />
                <div className="flex min-w-0 flex-1 flex-col gap-2 px-4 py-3.5">
                  {index === queue.length && history.length > 0 && <h2 className="text-base font-bold">Reviewed history</h2>}
                  <div className="flex flex-wrap items-center gap-2.5">
                    <span className={`rounded-full px-2.5 py-[3px] text-xs font-bold ${st.chipCls}`}>{st.chip}</span>
                    <span className="text-[15px] font-bold">{q.name}</span>
                    <span className="text-[13px] text-mute">{q.demo}</span>
                    {q.origin === "demo" && (
                      <span className="rounded-md bg-chip px-2 py-0.5 text-[11.5px] font-semibold text-mute">Demo data</span>
                    )}
                    {q.origin === "local" && (
                      <span className="rounded-md bg-chip px-2 py-0.5 text-[11.5px] font-semibold text-mute">Browser only · not saved</span>
                    )}
                    <span className="ml-auto text-[12.5px] text-mute-2">
                      Received {q.time} · {q.from}
                    </span>
                  </div>
                  <section aria-label="Kliininen yhteenveto" lang="fi" className="text-sm leading-normal text-ink-2">
                    <p className="m-0 font-semibold">{q.clinicalExplanation?.summary_fi || q.summary || "Tallennettua kliinistä yhteenvetoa ei ole saatavilla."}</p>
                    {q.clinicalExplanation?.findings.slice(0, 3).map(f => <p key={f.key} className="m-0">{f.text_fi}</p>)}
                    {!q.clinicalExplanation && q.origin === "backend" && <p className="text-xs text-mute">Rakenteinen suomenkielinen selitys ei ole saatavilla; näytetään tallennettu yhteenveto.</p>}
                  </section>
                  {q.analysis?.sourceObservations?.filter(o => o.numeric_value !== null).map(o => <p key={o.id} className="m-0 text-sm">{o.code}: {formatMeasurement(o.numeric_value, o.unit)} · {displayDate(o.observed_at)}</p>)}
                  {completed.length > 0 && <section aria-label="Completed tests" className="text-sm">
                    <strong>Kirjatut valmistuneet tutkimukset</strong>
                    {completed.map(o => <p key={o.id} className="m-0">{o.code ?? "Tutkimus"} · {formatMeasurement(o.numeric_value, o.unit)} · {displayDate(o.observed_at)} · completed</p>)}
                    <p className="m-0 text-mute">A completed test does not imply a recommendation to repeat it.</p>
                  </section>}
                  {q.clinicalExplanation && <ClinicalExplanationCard value={q.clinicalExplanation} triggeredRuleIds={q.analysis?.triggeredRuleIds} showSummary={false} />}
                  {q.cs && q.findings.length > 0 && <Reasons item={q} />}
                  {q.analysis?.qcancer && <QCancerEstimateCard estimate={q.analysis.qcancer} />}
                  {q.analysis && <AnalysisEvidence analysis={q.analysis} />}
                  {q.status === "reviewed" && !decision && <span>Reviewed · saved decision unavailable</span>}
                  {decision ? (
                    <span className="text-[13.5px] font-semibold text-ok">
                      Decided: {decision}
                      {q.origin === "backend" && <span className="font-normal text-mute-2"> (saved simulation)</span>}
                    </span>
                  ) : q.status !== "reviewed" ? (
                    <details className="text-sm">
                      <summary className="cursor-pointer font-semibold">Record a simulated decision</summary>
                      <p className="text-mute">These are clinician-selected recording options, not recommendations. Review the existing results before choosing an action.</p>
                      <div className="flex flex-wrap gap-2">
                      {actions.map(([label, result]) => (
                        <button
                          key={label}
                          type="button"
                          onClick={() => onDecide(q.key, result)}
                          disabled={!!busy || loading}
                          className="min-h-11 cursor-pointer rounded-lg border border-field bg-white px-3.5 py-2 text-[13.5px] font-semibold text-ink"
                        >
                          {busy === q.key ? "Saving decision…" : result === "fit_ordered" && completedFit ? "Simulate repeat FIT (clinician choice)" : label}
                        </button>
                      ))}
                      </div>
                    </details>
                  ) : null}
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
