import type { ReactNode } from "react";

import type { AnalysisResult, DataSource, Patient, PatientRecord } from "../lib/types";
import { FindingsPanel, QCancerEstimateCard } from "./FindingsPanel";
import { UrgentModal } from "./UrgentModal";

type Load<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: string };

export type NurseState = {
  source: DataSource;
  useCS: boolean;
  patients: Load<Patient[]>;
  patient: Patient | null;
  pid: string;
  record: Load<PatientRecord> | null;
  tab: "notes" | "lab" | "med" | "ref";
  note: string;
  saving: boolean;
  saved: boolean;
  saveError: string;
  result: AnalysisResult | null;
  pending: boolean;
  unresolved: boolean;
  panelOpen: boolean;
  sent: boolean;
  sending: boolean;
  sendError: string;
  sendNotice: string;
  dismissed: string;
  choosing: boolean;
  reason: string;
  blocked: boolean;
  checkedAt: string;
};

export type NurseHandlers = {
  pickPatient: (id: string) => void;
  tab: (t: NurseState["tab"]) => void;
  note: (text: string) => void;
  save: () => void;
  ack: () => void;
  close: () => void;
  send: () => void;
  dismiss: () => void;
  reason: (r: string) => void;
  confirmDismiss: () => void;
  cancelDismiss: () => void;
  toDoctor: () => void;
  retry: () => void;
  usePrototype?: () => void;
};

const TABS: [NurseState["tab"], string][] = [
  ["notes", "Notes"],
  ["lab", "Lab results"],
  ["med", "Medication"],
  ["ref", "Referrals"],
];

function StatusPill({ s }: { s: NurseState }) {
  const res = s.result;
  let dot = "bg-[#16A34A] ring-[#DCFCE7]";
  let text = s.saved ? `checked ${s.checkedAt}` : "monitoring notes";
  let title = "CancerSignal active";
  if (s.saving) {
    dot = "bg-mute-3 ring-chip";
    text = "checking…";
  } else if (res?.status === "unavailable" || s.patients.status === "error") {
    dot = "bg-mute-3 ring-chip";
    title = "CancerSignal unavailable";
    text = s.patients.status === "error" ? "backend not reachable" : "this note was not checked";
  } else if (s.pending) {
    dot = res?.status === "urgent" ? "bg-[#DC2626] ring-[#FEE2E2]" : "bg-amber-edge ring-amber-soft";
    text = "1 unread alert";
  }
  return (
    <div role="status" className="flex items-center gap-2 rounded-full bg-white px-3 py-1.5 text-[12.5px] text-ink">
      <span className={`h-[9px] w-[9px] rounded-full ring-3 ${dot}`} aria-hidden="true" />
      <span>
        <strong className="font-semibold">{title}</strong> · {text}
      </span>
    </div>
  );
}

function CsBadge({ id }: { id: string }) {
  return <span className="rounded-md bg-badge-bg px-2 py-0.5 text-[11.5px] font-bold text-badge-fg">CancerSignal {id}</span>;
}

function Notice({ children, tone = "info" }: { children: ReactNode; tone?: "info" | "error" }) {
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className={`rounded-xl border p-4 text-sm ${tone === "error" ? "border-red-line bg-red-soft text-red-ink" : "border-line bg-white text-mute"}`}
    >
      {children}
    </div>
  );
}

export function NurseView({ s, on }: { s: NurseState; on: NurseHandlers }) {
  const res = s.result;
  const lit = s.panelOpen && !!res;
  const findingFor = (id: string) => (lit ? res!.findings.find((f) => f.sources.some((x) => x.id === id)) : undefined);

  return (
    <>
      <header className="flex flex-wrap items-center gap-4 bg-header px-6 py-2.5 text-white">
        <span className="text-[15px] font-bold tracking-[0.01em]">Health Centre · Patient Record System</span>
        <span className="text-[12.5px] text-[#D1D5DB]">(fictional demo)</span>
        <span className="ml-auto text-[13px] text-[#E5E7EB]">Nurse H. Virtanen · Room 2</span>
        {s.useCS && <StatusPill s={s} />}
      </header>

      {s.pending && res?.status === "review" && s.patient && (
        <div role="alert" className="cs-banner flex flex-wrap items-center gap-3.5 border-b-2 border-amber-edge bg-amber-banner px-6 py-3.5">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#78350F" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
            <circle cx="12" cy="12" r="10" />
            <path d="M12 7v6M12 16.5v.5" />
          </svg>
          <div className="flex flex-[1_1_300px] flex-col gap-0.5">
            <span className="text-[17px] font-bold text-amber-ink">CancerSignal: physician review suggested for {s.patient.name}</span>
            <span className="text-sm text-amber-ink">{res.findings.length} findings in earlier records that may need attention.</span>
          </div>
          <button type="button" onClick={on.ack} className="min-h-12 cursor-pointer rounded-[10px] border-0 bg-amber-ink px-5.5 py-2.5 text-[15px] font-bold text-white">
            Open findings
          </button>
        </div>
      )}

      <div className="flex flex-1 flex-wrap items-stretch">
        <nav aria-label="Today's appointments" className="box-border flex flex-[1_1_270px] flex-col gap-1.5 border-r border-line bg-side px-3 py-4 md:flex-[0_0_270px]">
          <div className="flex items-baseline justify-between px-1.5 pb-1.5">
            <span className="text-sm font-bold">Appointments</span>
            <span className="text-[12.5px] text-mute-2">Sat 14 Nov 2026</span>
          </div>
          {s.patients.status === "loading" && <span className="px-1.5 text-sm text-mute-2">Loading patients…</span>}
          {s.patients.status === "ready" && s.patients.data.length === 0 && (
            <span className="px-1.5 text-sm text-mute-2">No patients in the backend. Run the synthetic seed.</span>
          )}
          {s.patients.status === "ready" &&
            s.patients.data.map((p) => {
              const active = p.id === s.pid;
              return (
                <button
                  key={p.id}
                  type="button"
                  onClick={() => on.pickPatient(p.id)}
                  aria-pressed={active}
                  className={`flex min-h-11 cursor-pointer items-start gap-3 rounded-[10px] border px-3 py-2.5 text-left ${
                    active ? "border-brand bg-brand-soft" : "border-line bg-white"
                  } ${s.unresolved && !active ? "opacity-55" : ""}`}
                >
                  <span className="min-w-10 text-[13px] font-semibold text-mute">{p.time}</span>
                  <span className="flex flex-1 flex-col gap-0.5">
                    <span className="text-sm font-semibold text-ink">{p.name}</span>
                    <span className="text-[12.5px] text-mute-2">
                      {p.demo} · {p.visit}
                    </span>
                  </span>
                  {active && s.pending && (
                    <span className="mt-0.5 flex items-center gap-1 text-[11.5px] font-semibold text-mute">
                      <span className={`h-2.5 w-2.5 rounded-full ${res?.status === "urgent" ? "bg-[#DC2626]" : "bg-amber-edge"}`} aria-hidden="true" />
                      Alert
                    </span>
                  )}
                </button>
              );
            })}
        </nav>

        <main className="box-border flex min-w-0 flex-[999_1_480px] flex-col gap-4 px-6 py-4.5">
          {s.patients.status === "error" && (
            <Notice tone="error">
              <p className="m-0 font-semibold">Patient list could not be loaded.</p>
              <p className="mt-1 mb-3">{s.patients.error}</p>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={on.retry} className="min-h-11 cursor-pointer rounded-lg border border-red-main bg-white px-4 text-sm font-semibold text-red-ink">
                  Try again
                </button>
                {on.usePrototype && (
                  <button type="button" onClick={on.usePrototype} className="min-h-11 cursor-pointer rounded-lg border-0 bg-header px-4 text-sm font-semibold text-white">
                    Use prototype data instead
                  </button>
                )}
              </div>
            </Notice>
          )}

          {s.patient && (
            <>
              <div className="flex flex-wrap items-baseline gap-3.5">
                <h1 className="m-0 text-xl font-bold">{s.patient.name}</h1>
                <span className="text-[13.5px] text-mute">
                  {s.patient.demo} · Patient no. {s.source === "backend" ? s.patient.id.slice(0, 8) : s.patient.id}
                </span>
                <span className="text-[13.5px] text-mute">Reason for visit: {s.patient.visit}</span>
              </div>

              <div role="tablist" aria-label="Patient record sections" className="flex flex-wrap gap-1 border-b border-line">
                {TABS.map(([k, label]) => {
                  const active = s.tab === k;
                  return (
                    <button
                      key={k}
                      type="button"
                      role="tab"
                      aria-selected={active}
                      onClick={() => on.tab(k)}
                      className={`min-h-11 cursor-pointer border-0 border-b-2 bg-transparent px-3.5 py-2.5 text-[13.5px] ${
                        active ? "border-brand font-semibold text-brand-dark" : "border-transparent font-normal text-mute"
                      }`}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>

              {s.tab === "notes" && (
                <section aria-label="New note" className="flex flex-col gap-2.5 rounded-xl border border-line bg-white p-4.5">
                  <div className="flex flex-wrap items-baseline justify-between gap-2">
                    <h2 className="m-0 text-base font-bold">New nursing note</h2>
                    <span className="text-[12.5px] text-mute-2">14 Nov 2026 · Nurse</span>
                  </div>
                  <label htmlFor="note" className="text-[12.5px] text-mute">
                    Nursing note
                  </label>
                  <textarea
                    id="note"
                    value={s.note}
                    onChange={(e) => on.note(e.target.value)}
                    rows={5}
                    placeholder="Write the nursing note…"
                    className="resize-y rounded-lg border border-field px-3 py-2.5 font-sans text-[14.5px] leading-[1.55] text-ink"
                  />
                  <div className="flex flex-wrap items-center gap-2.5">
                    <button
                      type="button"
                      onClick={on.save}
                      disabled={s.saving}
                      className="min-h-11 cursor-pointer rounded-lg border-0 bg-header px-5.5 py-2.5 text-sm font-semibold text-white disabled:cursor-wait disabled:opacity-70"
                    >
                      Save
                    </button>
                    <span aria-live="polite" className="flex flex-col gap-0.5">
                      {s.saving && <span className="text-[13px] text-mute">Checking earlier records…</span>}
                      {s.saved && <span className="text-[13px] text-ok">Note saved.</span>}
                      {s.saveError && <span className="text-[13px] font-semibold text-red-main">{s.saveError}</span>}
                      {s.useCS && res?.status === "unavailable" && (
                        <span className="text-[13px] text-mute">CancerSignal could not check this note{res.error ? `: ${res.error}` : "."}</span>
                      )}
                    </span>
                  </div>
                </section>
              )}

              <RecordSection s={s} findingFor={findingFor} />
              {res?.status === "none" && res.qcancer && (
                <section aria-label="CancerSignal model results" className="flex flex-col gap-2 rounded-xl border border-line bg-white p-4.5">
                  <h2 className="m-0 text-base font-bold">No evidence-table review alert</h2>
                  <p className="m-0 text-[13.5px] leading-[1.45] text-mute">The QCancer estimate is shown separately for this synthetic demo. It does not set or route a review alert.</p>
                  <QCancerEstimateCard estimate={res.qcancer} />
                </section>
              )}
            </>
          )}
        </main>

        {s.panelOpen && res && <FindingsPanel s={s} on={on} />}
      </div>

      {s.pending && res?.status === "urgent" && s.patient && <UrgentModal patient={s.patient} result={res} onOpen={on.ack} />}
    </>
  );
}

function RecordSection({ s, findingFor }: { s: NurseState; findingFor: (id: string) => { id: string } | undefined }) {
  if (!s.record || s.record.status === "loading") return <span className="text-sm text-mute-2">Loading patient record…</span>;
  if (s.record.status === "error") {
    return (
      <Notice tone="error">
        <p className="m-0 font-semibold">Patient record could not be loaded.</p>
        <p className="mt-1 mb-0">{s.record.error}</p>
      </Notice>
    );
  }
  const r = s.record.data;

  if (s.tab === "notes") {
    return (
      <section aria-label="Earlier entries" className="flex flex-col gap-2.5">
        <h2 className="m-0 text-[13px] font-semibold tracking-[0.06em] text-mute-2 uppercase">Earlier entries</h2>
        {r.history.length === 0 && <span className="text-sm text-mute-2">No earlier entries.</span>}
        {r.history.map((h) => {
          const f = findingFor(h.id);
          return (
            <article key={h.id} className={`flex flex-col gap-1 rounded-xl border px-4 py-3 ${f ? "border-hot-line bg-hot-bg" : "border-line bg-white"}`}>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[12.5px] font-semibold text-mute">{h.date}</span>
                <span className="rounded-md bg-chip px-[7px] py-0.5 text-[11.5px] font-semibold text-mute">{h.kind}</span>
                <span className="text-[11.5px] text-mute-3">{h.ref}</span>
                {f && (
                  <span className="ml-auto">
                    <CsBadge id={f.id} />
                  </span>
                )}
              </div>
              <span className="text-sm leading-normal text-ink-2">{h.text}</span>
            </article>
          );
        })}
      </section>
    );
  }

  if (s.tab === "lab") {
    return (
      <section aria-label="Lab results" className="overflow-x-auto rounded-xl border border-line bg-white">
        <table className="w-full min-w-[560px] border-collapse text-sm">
          <thead>
            <tr className="bg-side text-left">
              {["Date", "Test", "Result", "Reference", "Note"].map((c) => (
                <th key={c} className="px-3.5 py-2.5 text-[12.5px] font-semibold text-mute">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {r.labs.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3.5 py-2.5 text-mute-2">
                  No lab results.
                </td>
              </tr>
            )}
            {r.labs.map((l, i) => {
              const f = findingFor(l.id);
              return (
                <tr key={`${l.id}-${i}`} className={`border-t border-line-2 ${f ? "bg-hot-bg" : "bg-white"}`}>
                  <td className="px-3.5 py-2.5 text-mute">{l.date}</td>
                  <td className="px-3.5 py-2.5 font-semibold">{l.test}</td>
                  <td className={`px-3.5 py-2.5 ${l.flag ? "font-bold text-[#9A3412]" : "font-normal text-ink"}`}>
                    {l.value} {l.flag && <span aria-label={l.flag === "L" ? "low" : "high"}>{l.flag}</span>}
                  </td>
                  <td className="px-3.5 py-2.5 text-mute-2">{l.range || "—"}</td>
                  <td className="px-3.5 py-2.5 text-mute-2">
                    {l.note}
                    {f && (
                      <span className="ml-2">
                        <CsBadge id={f.id} />
                      </span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </section>
    );
  }

  if (s.tab === "med") {
    return (
      <section aria-label="Medication" className="flex flex-col gap-2.5">
        {r.meds.length === 0 && <span className="text-sm text-mute-2">No regular medication.</span>}
        {r.meds.map((m, i) => (
          <article key={i} className="flex flex-wrap items-baseline gap-x-4 gap-y-1.5 rounded-xl border border-line bg-white px-4 py-3">
            <span className="text-[14.5px] font-semibold">{m.name}</span>
            <span className="text-[13.5px] text-mute">{m.dose}</span>
            <span className="ml-auto text-[12.5px] text-mute-2">{m.status}</span>
          </article>
        ))}
      </section>
    );
  }

  return (
    <section aria-label="Referrals and test requests" className="flex flex-col gap-2.5">
      {r.refs.length === 0 && <span className="text-sm text-mute-2">No referrals or open test requests.</span>}
      {r.refs.map((ref, i) => (
        <article key={i} className="flex flex-col gap-1 rounded-xl border border-line bg-white px-4 py-3">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12.5px] font-semibold text-mute">{ref.date}</span>
            <span className="text-[14.5px] font-semibold">{ref.title}</span>
            <span className={`ml-auto rounded-full px-2.5 py-[3px] text-xs font-semibold ${ref.open ? "bg-amber-soft text-amber-dark" : "bg-chip text-mute"}`}>
              {ref.status}
            </span>
          </div>
          <span className="text-[13.5px] text-mute">{ref.detail}</span>
        </article>
      ))}
    </section>
  );
}
