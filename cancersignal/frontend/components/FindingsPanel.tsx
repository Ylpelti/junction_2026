import type { NurseHandlers, NurseState } from "./NurseView";
import { DISMISSAL_REASONS } from "../lib/api";
import type { QCancerEstimate } from "../lib/types";

const REASONS = Object.values(DISMISSAL_REASONS);

export function QCancerEstimateCard({ estimate }: { estimate: QCancerEstimate }) {
  return (
    <section aria-label="QCancer synthetic model estimate" className="flex flex-col gap-1 rounded-[10px] border border-line-2 bg-side px-3.5 py-3 text-[13.5px] leading-[1.45]">
      <strong>QCancer numerical estimate · synthetic demo</strong>
      {estimate.status === "calculated" ? (
        <span>{estimate.horizonYears}-year estimate: colorectal {estimate.colorectalCancerRiskPercent ?? "—"}% · all included cancer sites {estimate.anyCancerRiskPercent ?? "—"}%.</span>
      ) : (
        <span>Not calculated because required information is missing or outside the model’s supported range. Check the source records.</span>
      )}
      {(estimate.missingInputs.length > 0 || estimate.uncertainty) && <details>
        <summary className="cursor-pointer">Research model limitations and unavailable inputs</summary>
        {estimate.missingInputs.length > 0 && <p className="break-words">Unavailable inputs: {estimate.missingInputs.join(", ")}</p>}
        {estimate.uncertainty && <p>{estimate.uncertainty}</p>}
      </details>}
      <span className="text-xs text-mute-2">UK model. Townsend is set to 0 for this synthetic demo; the estimate is not calibrated for Finland and does not set the review alert.</span>
    </section>
  );
}

export function FindingsPanel({ s, on }: { s: NurseState; on: NurseHandlers }) {
  const res = s.result!;
  const canRequest = s.unresolved && !s.choosing;

  return (
    <aside
      aria-label="CancerSignal"
      className="box-border flex min-w-0 flex-[1_1_420px] flex-col gap-3.5 border-l border-line bg-white px-5 py-4.5 shadow-[-8px_0_24px_rgba(17,24,39,0.08)] lg:flex-[0_1_420px]"
    >
      <div className="flex items-center gap-2.5">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-brand">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#FFFFFF" strokeWidth="2.4" strokeLinecap="round" aria-hidden="true">
            <circle cx="5" cy="12" r="2" />
            <circle cx="19" cy="6" r="2" />
            <circle cx="19" cy="18" r="2" />
            <path d="M7 11l10-4M7 13l10 4" />
          </svg>
        </div>
        <span className="text-[15px] font-bold">CancerSignal</span>
        {!s.unresolved && (
          <button
            type="button"
            onClick={on.close}
            aria-label="Close CancerSignal panel"
            className="ml-auto flex h-11 w-11 cursor-pointer items-center justify-center rounded-lg border border-line bg-white"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#374151" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        )}
      </div>

      {res.origin === "prototype" && (
        <span className="self-start rounded-md bg-chip px-2 py-1 text-xs font-semibold text-mute">Prototype demo data · not from the backend</span>
      )}

      {s.unresolved && s.blocked && (
        <div role="alert" className="rounded-[10px] bg-bar px-3.5 py-3 text-[13.5px] leading-[1.45] text-white">
          <strong>Respond to this alert before moving on.</strong> Send it to the physician or dismiss it with a reason.
        </div>
      )}

      {res.status === "urgent" ? (
        <div className="flex flex-col gap-1 rounded-[10px] border border-red-line bg-red-soft p-3.5">
          <span className="flex items-center gap-2 text-base font-bold text-red-ink">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#B91C1C" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 3l10 18H2z" />
              <path d="M12 10v5M12 18v.5" />
            </svg>
            Urgent physician review
          </span>
          <span className="text-[13.5px] leading-[1.45] text-red-ink">{res.summary}</span>
        </div>
      ) : (
        <div className="flex flex-col gap-1 rounded-[10px] bg-amber-soft p-3.5">
          <span className="text-base font-bold text-amber-dark">Physician review recommended</span>
          <span className="text-[13.5px] leading-[1.45] text-amber-dark">{res.summary}</span>
        </div>
      )}

      <div className="flex flex-col gap-2.5">
        {res.findings.map((f) => (
          <div key={f.id} className="flex flex-col gap-1.5 rounded-[10px] border border-line-2 px-3.5 py-3">
            <div className="flex items-center gap-2">
              <span className="rounded-md bg-badge-bg px-2 py-0.5 text-[11.5px] font-bold text-badge-fg">{f.id}</span>
              <span className="text-[14.5px] font-semibold">{f.title}</span>
              {f.priority === "urgent" && (
                <span className="ml-auto shrink-0 rounded-md border border-red-line bg-red-soft px-2 py-0.5 text-[11.5px] font-bold text-red-ink uppercase">
                  Urgent
                </span>
              )}
            </div>
            <span className="text-[13.5px] leading-[1.45] text-mute">{f.detail}</span>
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-mute-2">Sources:</span>
              {f.sources.length === 0 && <span className="text-xs text-mute-2">none verifiable</span>}
              {f.sources.map((src) => (
                <span key={src.id} className="rounded-md bg-chip px-[7px] py-0.5 text-xs font-semibold text-mute">
                  {src.label}
                </span>
              ))}
            </div>
            <span className="text-xs text-mute-2">
              Rule <strong className="text-ink">{f.rule}</strong>
              {f.ruleSrc && ` · ${f.ruleSrc}`}
            </span>
          </div>
        ))}
      </div>

      {res.missing.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h3 className="m-0 text-[12.5px] font-semibold tracking-[0.06em] text-mute-2 uppercase">Not found in records</h3>
          <ul className="m-0 flex flex-col gap-1 pl-4.5">
            {res.missing.map((m, i) => (
              <li key={i} className="text-[13.5px] text-ink-2">
                {m}
              </li>
            ))}
          </ul>
        </div>
      )}

      {s.sendError && (
        <div role="alert" className="rounded-[10px] border border-red-line bg-red-soft px-3.5 py-3 text-[13.5px] leading-[1.45] text-red-ink">
          {s.sendError} You can try again.
        </div>
      )}

      {canRequest && (
        <div className="flex flex-wrap gap-2.5">
          <button
            type="button"
            onClick={on.send}
            disabled={s.locked}
            className="min-h-11 cursor-pointer rounded-[10px] border-0 bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70"
          >
            {s.sending ? "Sending…" : s.sendError ? "Try sending again" : "Send to physician"}
          </button>
          <button
            type="button"
            onClick={on.dismiss}
            disabled={s.locked}
            className="min-h-11 cursor-pointer rounded-[10px] border border-line-3 bg-white px-4 py-2.5 text-sm font-semibold text-ink"
          >
            Dismiss with reason
          </button>
        </div>
      )}

      {s.sent && (
        <div className="flex flex-col gap-2 rounded-[10px] border border-brand-line bg-brand-tint px-3.5 py-3 text-[13.5px] leading-[1.45] text-brand-dark">
          <span>
            <strong>Sent to the physician.</strong> The findings and their source records go with it. The physician decides on a stool blood
            test (FIT), referral or no action.
          </span>
          {s.sendNotice && <span className="font-semibold">{s.sendNotice}</span>}
          <button
            type="button"
            onClick={on.toDoctor}
            className="min-h-11 cursor-pointer self-start rounded-lg border border-brand bg-white px-3.5 py-2 text-[13.5px] font-semibold text-brand"
          >
            Open physician view
          </button>
        </div>
      )}

      {s.unresolved && s.choosing && (
        <fieldset className="m-0 flex flex-col gap-2 rounded-[10px] border border-line-3 px-3.5 py-3">
          <legend className="px-1 text-[13.5px] font-semibold">Reason for dismissing</legend>
          <div role="radiogroup" aria-label="Reason for dismissing" className="flex flex-col gap-2">
            {REASONS.map((label) => {
              const checked = s.reason === label;
              return (
                <button
                  key={label}
                  type="button"
                  role="radio"
                  aria-checked={checked}
                  onClick={() => on.reason(label)}
                  className={`min-h-11 cursor-pointer rounded-lg border px-3 py-2 text-left text-[13.5px] text-ink ${
                    checked ? "border-brand bg-brand-soft font-semibold" : "border-line-3 bg-white"
                  }`}
                >
                  {label}
                </button>
              );
            })}
          </div>
          <div className="mt-1 flex flex-wrap gap-2">
            <button
              type="button"
              onClick={on.confirmDismiss}
              disabled={!s.reason || s.locked}
              className="min-h-11 cursor-pointer rounded-[10px] border-0 bg-header px-4 py-2.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:bg-[#6B7280]"
            >
              {s.sending ? "Saving dismissal…" : "Confirm dismissal"}
            </button>
            <button
              type="button"
              onClick={on.cancelDismiss}
              className="min-h-11 cursor-pointer rounded-[10px] border border-line-3 bg-white px-4 py-2.5 text-sm font-semibold text-ink"
            >
              Cancel
            </button>
          </div>
        </fieldset>
      )}

      {s.dismissed && (
        <div className="rounded-[10px] border border-line-3 bg-side px-3.5 py-3 text-[13.5px] text-mute">
          Dismissed: {s.dismissed}. Synthetic workflow action.
        </div>
      )}

      <p className="m-0 border-t border-line-2 pt-3 text-xs leading-[1.45] text-mute-2">
        Decision support only. Deterministic rules with cited sources decide when to alert; the language model extracts and explains. No alert does not
        rule out cancer.
      </p>
    </aside>
  );
}
