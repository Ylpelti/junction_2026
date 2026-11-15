"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { FALLBACK_QUEUE, PROTOTYPE_PATIENTS } from "../data/fallback";
import { analyseSavedNote, ApiError, createNote, createReviewRequest, listObservations, listPatients, listReviewRequests, listAnalyses, getDismissal, getDecision, saveDismissal, saveDecision, DISMISSAL_REASONS, DECISION_ACTIONS, type DecisionAction, type DismissalReason } from "../lib/api";
import { ALLOW_PROTOTYPE_DATASET } from "../lib/flags";
import { toAnalysis, toPatient, toQueueItem, toRecord, type ApiAnalysisResponse, type ApiObservation } from "../lib/mappers";
import type { AnalysisResult, DataSource, Patient, PatientRecord, QueueItem } from "../lib/types";
import demoNotes from "../data/demo-notes.json";
import { DemoBar } from "./DemoBar";
import { NurseView, type NurseState } from "./NurseView";
import { PhysicianView } from "./PhysicianView";

type Load<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: string };
type Visit = {
  saving: boolean; saved: boolean; saveError: string; result: AnalysisResult | null;
  acked: boolean; closed: boolean; choosing: boolean; reason: string; blocked: boolean;
  checkedAt: string; sending: boolean; sendError: string; sendNotice: string;
};
const FRESH_VISIT: Visit = { saving: false, saved: false, saveError: "", result: null, acked: false, closed: false, choosing: false, reason: "", blocked: false, checkedAt: "", sending: false, sendError: "", sendNotice: "" };
const message = (e: unknown) => e instanceof Error ? e.message : "Unexpected error.";
const stamp = (iso: string) => new Date(iso).toLocaleString();
// Retain the original attempt identity in this browser tab across refreshes. It
// prevents a lost POST response from causing a second note to be submitted.
type Attempt = { patientId: string; text: string; at: string; noteId?: string; analyse: boolean };
const DRAFTS_KEY = "cancersignal.nurse-drafts.v1";
const ATTEMPT_KEY = "cancersignal.pending-note.v1";
function readAttempt(): Attempt | null {
  try { return JSON.parse(sessionStorage.getItem(ATTEMPT_KEY) ?? "null"); } catch { return null; }
}

export function CancerSignalApp() {
  const [view, setView] = useState<"nurse" | "doctor">("nurse");
  const [useCS, setUseCS] = useState(true);
  const [source, setSource] = useState<DataSource>("backend");
  const [patients, setPatients] = useState<Load<Patient[]>>({ status: "loading" });
  const [pid, setPid] = useState("");
  const [record, setRecord] = useState<Load<PatientRecord>>({ status: "loading" });
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<NurseState["tab"]>("notes");
  const [visit, setVisit] = useState<Visit>(FRESH_VISIT);
  const [analyses, setAnalyses] = useState<ApiAnalysisResponse[]>([]);
  const [selectedAnalysis, setSelectedAnalysis] = useState("");
  const [restoring, setRestoring] = useState(false);
  const [restoreError, setRestoreError] = useState("");
  const [sentAnalyses, setSentAnalyses] = useState<Record<string, string>>({});
  const [dismissals, setDismissals] = useState<Record<string, string>>({});
  const [sentItems, setSentItems] = useState<Record<string, QueueItem>>({});
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [backendQueue, setBackendQueue] = useState<Load<QueueItem[]>>({ status: "loading" });
  const [reviewed, setReviewed] = useState<QueueItem[]>([]);
  const [decisionBusy, setDecisionBusy] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const [reloadKey, setReloadKey] = useState(0);
  const [attempt, setAttempt] = useState<Attempt | null>(null);
  const busy = useRef(false);
  const selection = useRef(0);
  const queueVersion = useRef(0);
  const holdAttempt = (value: Attempt | null) => {
    if (value) sessionStorage.setItem(ATTEMPT_KEY, JSON.stringify(value));
    else sessionStorage.removeItem(ATTEMPT_KEY);
    setAttempt(value);
  };

  useEffect(() => {
    const pending = readAttempt();
    setAttempt(pending);
    try {
      const stored: unknown = JSON.parse(sessionStorage.getItem(DRAFTS_KEY) ?? "{}");
      const drafts = stored && typeof stored === "object" && !Array.isArray(stored)
        ? Object.fromEntries(Object.entries(stored).filter(([, text]) => typeof text === "string")) : {};
      if (pending) drafts[pending.patientId] = pending.text;
      setNotes(drafts);
    } catch { if (pending) setNotes({ [pending.patientId]: pending.text }); }
  }, []);
  const updateNote = (id: string, text: string) => {
    setNotes(previous => {
      const next = { ...previous, [id]: text };
      try { sessionStorage.setItem(DRAFTS_KEY, JSON.stringify(next)); } catch { /* In-memory draft remains editable. */ }
      return next;
    });
  };
  useEffect(() => {
    let live = true;
    setPatients({ status: "loading" });
    const load = source === "prototype" ? Promise.resolve(PROTOTYPE_PATIENTS.map(x => x.patient)) : listPatients().then(rows => rows.map(p => toPatient(p, undefined)));
    load.then(rows => {
      if (!live) return;
      setPatients({ status: "ready", data: rows });
      setPid(current => rows.some(p => p.id === current) ? current : rows[0]?.id ?? "");
    }).catch(e => live && setPatients({ status: "error", error: message(e) }));
    return () => { live = false; };
  }, [source, reloadKey]);

  useEffect(() => {
    const version = ++selection.current;
    setVisit(FRESH_VISIT); setAnalyses([]); setSelectedAnalysis(""); setRestoreError("");
    if (!pid) return;
    if (source === "prototype") {
      const demo = PROTOTYPE_PATIENTS.find(x => x.patient.id === pid);
      if (demo) setRecord({ status: "ready", data: demo.record });
      setRestoring(false);
      return;
    }
    setRestoring(true); setRecord({ status: "loading" });
    Promise.all([listObservations(pid), listAnalyses(pid), listReviewRequests("all", pid)]).then(async ([rows, runs, requests]) => {
      const saved = await Promise.all(runs.map(async run => [run.id, await getDismissal(run.id)] as const));
      if (version !== selection.current) return;
      setRecord({ status: "ready", data: toRecord(rows) });
      setAnalyses(runs); setSelectedAnalysis(runs[0]?.id ?? "");
      setSentAnalyses(Object.fromEntries(requests.map(r => [r.analysis_id, `Sent ${stamp(r.created_at)} · ${r.status}`])));
      setDismissals(Object.fromEntries(saved.filter(([, d]) => d).map(([id, d]) => [id, `${DISMISSAL_REASONS[d!.reason_code]} · ${d!.actor} · ${stamp(d!.created_at)}`])));
      if (runs[0]) setVisit({ ...FRESH_VISIT, saved: true, acked: true, result: toAnalysis(runs[0]), checkedAt: stamp(runs[0].created_at) });
    }).catch(e => {
      if (version !== selection.current) return;
      setRestoreError(`Saved patient state could not be loaded. ${message(e)}`);
      setRecord({ status: "error", error: message(e) });
    }).finally(() => { if (version === selection.current) setRestoring(false); });
    return () => { selection.current++; };
  }, [pid, source, reloadKey]);

  const refreshQueue = useCallback(async () => {
    if (source !== "backend") return;
    const version = ++queueVersion.current;
    setBackendQueue({ status: "loading" });
    setReviewed([]);
    try {
      const [pending, history] = await Promise.all([listReviewRequests("pending"), listReviewRequests("reviewed")]);
      const patientIds = [...new Set([...pending, ...history].map(r => r.patient_id))];
      const observations = new Map(await Promise.all(patientIds.map(async id => [id, await listObservations(id)] as const)));
      const mapRequest = (r: (typeof pending)[number]) => ({ ...toQueueItem(r), observations: observations.get(r.patient_id) });
      const actions = await Promise.all(history.map(async row => {
        const d = await getDecision(row.id);
        if (!d) throw new Error("A reviewed request has no saved decision. Refresh to reconcile.");
        return [row.id, `${DECISION_ACTIONS[d.action]} · ${d.actor} · ${stamp(d.created_at)}`] as const;
      }));
      if (version !== queueVersion.current) return;
      setBackendQueue({ status: "ready", data: pending.map(mapRequest) });
      setReviewed(history.map(mapRequest)); setDecisions(Object.fromEntries(actions));
    } catch (e) { if (version === queueVersion.current) setBackendQueue({ status: "error", error: message(e) }); }
  }, [source]);
  useEffect(() => { if (view === "doctor") void refreshQueue(); }, [view, refreshQueue]);

  const patientList = patients.status === "ready" ? patients.data : [];
  const patient = patientList.find(p => p.id === pid) ?? null;
  const res = visit.result;
  const actionKey = source === "backend" ? res?.analysisId ?? "" : `prototype-${pid}`;
  const sent = !!sentAnalyses[actionKey] || (source === "prototype" && !!sentItems[pid]);
  const dismissed = dismissals[actionKey] ?? "";
  const flagged = useCS && !!res && (res.status === "review" || res.status === "urgent");
  const unresolved = flagged && !sent && !dismissed;
  const locked = visit.saving || visit.sending || restoring || !!restoreError;
  const noteText = patient ? notes[pid] ?? (attempt?.patientId === pid ? attempt.text : undefined) ?? (source === "backend" ? (demoNotes as Record<string, string>)[pid] : undefined) ?? patient.draftNote : "";
  const queue = useMemo(() => source === "backend" ? backendQueue.status === "ready" ? backendQueue.data : [] : [...FALLBACK_QUEUE.map(q => ({ ...q, origin: "demo" as const })), ...Object.values(sentItems)], [source, backendQueue, sentItems]);

  const pickPatient = (id: string) => {
    if (id === pid || busy.current || visit.saving || visit.sending) return;
    setVisit(FRESH_VISIT); setPid(id);
  };
  const showAnalysis = (id: string) => {
    if (locked || busy.current) return;
    const run = analyses.find(r => r.id === id);
    setSelectedAnalysis(id);
    setVisit(run ? { ...FRESH_VISIT, saved: true, acked: true, result: toAnalysis(run), checkedAt: stamp(run.created_at) } : FRESH_VISIT);
  };
  const acceptRun = (run: ApiAnalysisResponse) => {
    setAnalyses(old => [run, ...old.filter(r => r.id !== run.id)]); setSelectedAnalysis(run.id);
    setVisit({ ...FRESH_VISIT, saved: true, result: toAnalysis(run), checkedAt: stamp(run.created_at) });
  };

  // Reconciliation never POSTs another note. A saved note can explicitly be
  // analysed by its UUID, but only after checking all saved runs for that note.
  const reconcile = async () => {
    if (!attempt || busy.current || attempt.patientId !== pid) return;
    busy.current = true; setVisit(v => ({ ...v, saving: true, saveError: "" }));
    try {
      const [rows, runs] = await Promise.all([listObservations(pid), listAnalyses(pid)]);
      setRecord({ status: "ready", data: toRecord(rows) });
      const matches = rows.filter(o => o.observation_type === "clinical_note" && o.text === attempt.text && Date.parse(o.observed_at) === Date.parse(attempt.at));
      const note = attempt.noteId ? rows.find(o => o.id === attempt.noteId) : matches.length === 1 ? matches[0] : undefined;
      if (!note) throw new Error("The original note is not yet confirmed in saved history. No note was resent. Refresh history again after the original request finishes.");
      const run = runs.find(r => r.provenance.input_observation_id === note.id);
      if (run) { acceptRun(run); holdAttempt(null); setReloadKey(k => k + 1); }
      else if (!attempt.analyse) { holdAttempt(null); setVisit({ ...FRESH_VISIT, saved: true }); }
      else { holdAttempt({ ...attempt, noteId: note.id }); setVisit(v => ({ ...v, saving: false, saveError: "Note confirmed. No analysis found. Use Analyse saved note when the original request has finished." })); }
    } catch (e) { setVisit(v => ({ ...v, saving: false, saveError: message(e) })); }
    finally { busy.current = false; }
  };
  const resumeAnalysis = async () => {
    if (!attempt?.noteId || attempt.patientId !== pid || busy.current) return;
    busy.current = true; setVisit(v => ({ ...v, saving: true, saveError: "" }));
    try {
      const runs = await listAnalyses(pid);
      const existing = runs.find(r => r.provenance.input_observation_id === attempt.noteId);
      acceptRun(existing ?? await analyseSavedNote(pid, attempt.noteId));
      holdAttempt(null); updateNote(pid, "");
    } catch (e) { setVisit(v => ({ ...v, saving: false, saveError: `Analysis could not be confirmed. Reconcile saved history before retrying. ${message(e)}` })); }
    finally { busy.current = false; }
  };
  const save = async () => {
    if (!patient || busy.current || locked || (source === "backend" && attempt)) return;
    const text = noteText.trim();
    if (!text) { setVisit(v => ({ ...v, saveError: "Write a note before saving." })); return; }
    busy.current = true; setVisit({ ...FRESH_VISIT, saving: true });
    if (source === "prototype") {
      const canned = PROTOTYPE_PATIENTS.find(x => x.patient.id === pid)?.analysis;
      setVisit({ ...FRESH_VISIT, saved: true, result: useCS && canned ? { ...canned, origin: "prototype" } : null });
      busy.current = false; return;
    }
    const pending: Attempt = { patientId: pid, text, at: new Date().toISOString(), analyse: useCS };
    let noteConfirmed = false;
    try {
      holdAttempt(pending);
      const note = await createNote({ patientId: pid, text, at: new Date(pending.at) });
      noteConfirmed = true;
      holdAttempt({ ...pending, noteId: note.id });
      if (useCS) acceptRun(await analyseSavedNote(pid, note.id));
      else setVisit({ ...FRESH_VISIT, saved: true });
      holdAttempt(null); updateNote(pid, "");
      setRecord({ status: "ready", data: toRecord(await listObservations(pid)) });
    } catch (e) {
      if (!noteConfirmed && e instanceof ApiError && [404, 409, 422].includes(e.status ?? 0)) {
        holdAttempt(null);
        setVisit(v => ({ ...v, saving: false, saveError: `The note was rejected by the backend. ${message(e)}` }));
        return;
      }
      setVisit(v => ({ ...v, saving: false, saveError: `Save could not be fully confirmed. Reconcile saved history; do not submit the note again. ${message(e)}` }));
    } finally { busy.current = false; }
  };
  const sendToPhysician = async () => {
    if (!patient || !res || !unresolved || locked || busy.current) return;
    if (source === "prototype") {
      setSentItems(s => ({ ...s, [pid]: { key: `prototype-${pid}`, name: patient.name, demo: patient.demo, time: stamp(new Date().toISOString()), from: "SYNTHETIC Nurse", level: res.status === "urgent" ? "urgent" : "review", cs: true, summary: res.summary, findings: res.findings, missing: res.missing, origin: "local" } })); return;
    }
    if (!res.analysisId) return;
    busy.current = true; setVisit(v => ({ ...v, sending: true, sendError: "" }));
    try {
      let request;
      try { request = await createReviewRequest(pid, res.analysisId, "SYNTHETIC Nurse H. Virtanen"); }
      catch (e) {
        request = (await listReviewRequests("all", pid)).find(r => r.analysis_id === res.analysisId);
        if (!request) {
          const d = await getDismissal(res.analysisId);
          if (d) setDismissals(old => ({ ...old, [d.analysis_id]: `${DISMISSAL_REASONS[d.reason_code]} · ${d.actor} · ${stamp(d.created_at)}` }));
          throw e;
        }
      }
      setSentAnalyses(old => ({ ...old, [request.analysis_id]: `Sent ${stamp(request.created_at)} · ${request.status}` }));
    } catch (e) { setVisit(v => ({ ...v, sendError: `Submission could not be confirmed. Retrying this analysis is safe. ${message(e)}` })); }
    finally { setVisit(v => ({ ...v, sending: false })); busy.current = false; }
  };
  const confirmDismiss = async () => {
    if (!patient || !unresolved || !visit.reason || busy.current || locked) return;
    if (source === "prototype") { setDismissals(d => ({ ...d, [actionKey]: `${visit.reason} · browser only` })); setVisit(v => ({ ...v, choosing: false })); return; }
    if (!res?.analysisId) return;
    busy.current = true; setVisit(v => ({ ...v, sending: true, sendError: "" }));
    try {
      const reason = (Object.keys(DISMISSAL_REASONS) as DismissalReason[]).find(code => DISMISSAL_REASONS[code] === visit.reason);
      if (!reason) throw new Error("Select a dismissal reason.");
      const saved = await saveDismissal(res.analysisId, pid, reason);
      setDismissals(d => ({ ...d, [saved.analysis_id]: `${DISMISSAL_REASONS[saved.reason_code]} · ${saved.actor} · ${stamp(saved.created_at)}` }));
      setVisit(v => ({ ...v, choosing: false }));
    } catch (e) {
      try { const requests = await listReviewRequests("all", pid); setSentAnalyses(Object.fromEntries(requests.map(r => [r.analysis_id, `Sent ${stamp(r.created_at)} · ${r.status}`]))); } catch { /* Original failure remains visible; no success inferred. */ }
      setVisit(v => ({ ...v, sendError: `Dismissal could not be confirmed. ${message(e)}` }));
    } finally { busy.current = false; setVisit(v => ({ ...v, sending: false })); }
  };
  const decide = async (key: string, action: DecisionAction) => {
    if (busy.current) return;
    if (source === "prototype") { setDecisions(d => ({ ...d, [key]: `${DECISION_ACTIONS[action]} · browser only` })); return; }
    const item = queue.find(q => q.key === key && q.origin === "backend" && q.status === "pending");
    if (!item) return;
    busy.current = true; setDecisionBusy(key); setDecisionError("");
    queueVersion.current++;
    try {
      const saved = await saveDecision(key, action);
      setDecisions(d => ({ ...d, [key]: `${DECISION_ACTIONS[saved.action]} · ${saved.actor} · ${stamp(saved.created_at)}` }));
      await refreshQueue();
    } catch (e) { setDecisionError(`Decision could not be confirmed. ${message(e)}`); }
    finally { busy.current = false; setDecisionBusy(""); }
  };
  const resetDemo = () => {
    if (busy.current) return;
    setBackendQueue({ status: "loading" }); setReviewed([]); setDecisionError("");
    setVisit(FRESH_VISIT); setSentItems({}); setDecisions({}); setDismissals({}); setSentAnalyses({}); setTab("notes"); setReloadKey(k => k + 1);
  };
  const state: NurseState = {
    source, useCS, patients, patient, pid, record, tab, note: noteText,
    ...visit, result: res, pending: flagged && !visit.acked && !sent && !dismissed,
    unresolved, panelOpen: flagged && visit.acked && !visit.closed, sent, dismissed,
    sendNotice: sentAnalyses[actionKey] ?? "", locked, restoring, restoreError,
    analyses: analyses.map(r => ({ id: r.id, label: `${stamp(r.created_at)} · ${r.status}` })), selectedAnalysis,
    pendingAttempt: source === "backend" && !!attempt,
    canReconcile: attempt?.patientId === pid, canResume: attempt?.patientId === pid && !!attempt?.noteId,
  };
  return (
    <div className="flex min-h-screen flex-col bg-page text-ink">
      <DemoBar view={view} onView={v => { if (!busy.current) setView(v); }} useCS={useCS}
        onToggleCS={() => { if (!busy.current) setUseCS(v => !v); }} source={source}
        onSource={ALLOW_PROTOTYPE_DATASET ? s => { if (!busy.current && s !== source) { resetDemo(); setPid(""); setSource(s); queueVersion.current++; } } : undefined}
        onReset={resetDemo} />
      <p role="status" className="m-0 border-b border-line bg-side px-6 py-2 text-sm text-mute">
        {source === "backend" ? "Backend demo · canonical PostgreSQL patients only. Legacy datasets are excluded." : "Prototype only · canned patients and findings; actions are not saved to PostgreSQL."}
      </p>
      {view === "nurse" ? <NurseView s={state} on={{
        pickPatient, tab: setTab, note: text => { if (!busy.current) updateNote(pid, text); }, save,
        ack: () => setVisit(v => ({ ...v, acked: true, closed: false })), close: () => setVisit(v => ({ ...v, closed: true })),
        send: sendToPhysician, dismiss: () => { if (!locked) setVisit(v => ({ ...v, choosing: true })); },
        reason: reason => setVisit(v => ({ ...v, reason })), confirmDismiss,
        cancelDismiss: () => { if (!busy.current) setVisit(v => ({ ...v, choosing: false, reason: "" })); },
        toDoctor: () => setView("doctor"), retry: () => { if (!busy.current) setReloadKey(k => k + 1); },
        selectAnalysis: showAnalysis, reconcile, resumeAnalysis,
        usePrototype: ALLOW_PROTOTYPE_DATASET ? () => { if (!busy.current) { setPid(""); setSource("prototype"); } } : undefined,
      }} /> : <PhysicianView queue={queue} history={source === "backend" ? reviewed : []} decisions={decisions} onDecide={decide}
        loading={source === "backend" && backendQueue.status === "loading"} busy={decisionBusy}
        notice={decisionError || (source === "backend" && backendQueue.status === "error" ? `Review queue unavailable. ${backendQueue.error}` : "")}
        onRefresh={source === "backend" ? () => { if (!busy.current) void refreshQueue(); } : undefined} />}
    </div>
  );
}
