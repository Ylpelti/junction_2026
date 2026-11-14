"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { FALLBACK_APPOINTMENTS, FALLBACK_QUEUE, PROTOTYPE_PATIENTS } from "../data/fallback";
import { analyseNote, ApiError, createNote, createReviewRequest, listObservations, listPatients, listReviewRequests } from "../lib/api";
import {
  ALLOW_PROTOTYPE_DATASET,
  USE_BACKEND_REVIEW_QUEUE,
  USE_FALLBACK_APPOINTMENTS,
  USE_FALLBACK_QUEUE,
  USE_LOCAL_WORKFLOW,
} from "../lib/flags";
import { toAnalysis, toPatient, toQueueItem, toRecord } from "../lib/mappers";
import type { AnalysisResult, DataSource, Patient, PatientRecord, QueueItem } from "../lib/types";
import { DemoBar } from "./DemoBar";
import { NurseView, type NurseState } from "./NurseView";
import { PhysicianView } from "./PhysicianView";

type Load<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "error"; error: string };

type Visit = {
  saving: boolean;
  saved: boolean;
  saveError: string;
  result: AnalysisResult | null;
  acked: boolean;
  closed: boolean;
  choosing: boolean;
  reason: string;
  blocked: boolean;
  checkedAt: string;
  sending: boolean;
  /** Send failed (e.g. 404/409/422); the alert is NOT sent. */
  sendError: string;
  /** Send fell back to browser-only state because the backend was unreachable. */
  sendNotice: string;
};

const FRESH_VISIT: Visit = {
  sending: false,
  sendError: "",
  sendNotice: "",
  saving: false,
  saved: false,
  saveError: "",
  result: null,
  acked: false,
  closed: false,
  choosing: false,
  reason: "",
  blocked: false,
  checkedAt: "",
};

const NURSE = "Nurse H. Virtanen";
const hhmm = (d = new Date()) => `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
const message = (e: unknown) => (e instanceof ApiError ? e.message : "Unexpected error.");
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));

export function CancerSignalApp() {
  const [view, setView] = useState<"nurse" | "doctor">("nurse");
  const [useCS, setUseCS] = useState(true);
  const [source, setSource] = useState<DataSource>("backend");
  const [patients, setPatients] = useState<Load<Patient[]>>({ status: "loading" });
  const [pid, setPid] = useState<string>("");
  const [records, setRecords] = useState<Record<string, Load<PatientRecord>>>({});
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [tab, setTab] = useState<NurseState["tab"]>("notes");
  const [visit, setVisit] = useState<Visit>(FRESH_VISIT);
  // Browser-only sends (prototype data, or backend unreachable). Backend sends live in the review API.
  const [sentItems, setSentItems] = useState<Record<string, QueueItem>>({});
  // Backend sends: patient id -> analysis id that was submitted for review.
  const [sentAnalyses, setSentAnalyses] = useState<Record<string, string>>({});
  // TODO(backend): no endpoint for dismissal with reason; browser state only (USE_LOCAL_WORKFLOW).
  const [dismissedFor, setDismissedFor] = useState<Record<string, string>>({});
  // TODO(backend): no endpoint for physician decisions; browser state only, shown as "not saved".
  const [decisions, setDecisions] = useState<Record<string, string>>({});
  const [backendQueue, setBackendQueue] = useState<Load<QueueItem[]> | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // ---- Data loading ------------------------------------------------------

  useEffect(() => {
    let live = true;
    setRecords({});
    setVisit(FRESH_VISIT);
    if (source === "prototype") {
      const list = PROTOTYPE_PATIENTS.map((x) => x.patient);
      setPatients({ status: "ready", data: list });
      setRecords(Object.fromEntries(PROTOTYPE_PATIENTS.map((x) => [x.patient.id, { status: "ready", data: x.record }])));
      setPid(list[0].id);
      return;
    }
    setPatients({ status: "loading" });
    listPatients()
      .then((rows) => {
        if (!live) return;
        // TODO(backend): appointment time/reason for visit come from fallback (USE_FALLBACK_APPOINTMENTS).
        const list = rows.map((p, i) => toPatient(p, USE_FALLBACK_APPOINTMENTS ? FALLBACK_APPOINTMENTS[i] : undefined));
        setPatients({ status: "ready", data: list });
        setPid(list[0]?.id ?? "");
      })
      .catch((e) => live && setPatients({ status: "error", error: message(e) }));
    return () => {
      live = false;
    };
  }, [source, reloadKey]);

  const loadRecord = useCallback(
    (id: string) => {
      if (source !== "backend" || !id) return;
      setRecords((r) => ({ ...r, [id]: r[id]?.status === "ready" ? r[id] : { status: "loading" } }));
      listObservations(id)
        .then((rows) => setRecords((r) => ({ ...r, [id]: { status: "ready", data: toRecord(rows) } })))
        .catch((e) => setRecords((r) => ({ ...r, [id]: { status: "error", error: message(e) } })));
    },
    [source],
  );

  useEffect(() => {
    if (source === "backend" && pid && !records[pid]) loadRecord(pid);
  }, [pid, source, records, loadRecord]);

  // ---- Derived state (mirrors the prototype) -----------------------------

  const patientList = patients.status === "ready" ? patients.data : [];
  const patient = patientList.find((p) => p.id === pid) ?? null;
  const res = visit.result;
  const flagged = visit.saved && !!res && (res.status === "review" || res.status === "urgent");
  const pending = flagged && !visit.acked;
  const sent = !!sentItems[pid] || (!!res?.analysisId && sentAnalyses[pid] === res.analysisId);
  const dismissed = dismissedFor[pid];
  const unresolved = flagged && !sent && !dismissed;
  const panelOpen = flagged && visit.acked && !visit.closed;

  // Backend review queue only for backend data with CancerSignal on; otherwise the local workflow.
  const useBackendQueue = USE_BACKEND_REVIEW_QUEUE && source === "backend" && useCS;

  const refreshQueue = useCallback(() => {
    if (!useBackendQueue) return;
    setBackendQueue((q) => (q?.status === "ready" ? q : { status: "loading" }));
    listReviewRequests()
      .then((rows) => setBackendQueue({ status: "ready", data: rows.map(toQueueItem) }))
      .catch((e) => setBackendQueue({ status: "error", error: message(e) }));
  }, [useBackendQueue]);

  // Load the queue whenever the physician view opens.
  useEffect(() => {
    if (view === "doctor") refreshQueue();
  }, [view, refreshQueue]);

  const demoItems = useMemo(() => (USE_FALLBACK_QUEUE ? FALLBACK_QUEUE : []).map((x) => ({ ...x, origin: "demo" as const })), []);
  const localSent = useMemo(() => Object.values(sentItems), [sentItems]);

  const queue = useMemo(() => {
    if (useBackendQueue && backendQueue?.status === "ready") {
      // Keep the backend order (urgent → review → normal, oldest first); do not re-sort.
      // Fallback routine items follow, marked as demo data; browser-only sends last.
      return [...backendQueue.data, ...demoItems.filter((x) => !x.cs), ...localSent];
    }
    const rank = { urgent: 0, review: 1, normal: 2 } as const;
    const items = [...demoItems.filter((x) => useCS || !x.cs), ...(useCS && USE_LOCAL_WORKFLOW ? localSent : [])];
    return items.sort((a, b) => rank[a.level] - rank[b.level] || a.time.localeCompare(b.time));
  }, [useBackendQueue, backendQueue, demoItems, localSent, useCS]);

  const queueNotice =
    useBackendQueue && backendQueue?.status === "error"
      ? `Physician review queue could not be loaded from the backend (${backendQueue.error}). Showing the browser-only queue; it is not saved.`
      : "";
  const queueLoading = useBackendQueue && backendQueue?.status === "loading";

  // ---- Actions -----------------------------------------------------------

  const resetVisit = () => setVisit(FRESH_VISIT);

  const pickPatient = (id: string) => {
    if (id === pid || visit.saving || visit.sending) return;
    if (unresolved) {
      setVisit((v) => ({ ...v, blocked: true, acked: true, closed: false }));
      return;
    }
    resetVisit();
    setPid(id);
  };

  const noteText = patient ? (notes[patient.id] ?? patient.draftNote) : "";

  const save = async () => {
    if (!patient || visit.saving) return;
    const text = noteText.trim();
    if (!text) {
      setVisit({ ...FRESH_VISIT, saveError: "Write a note before saving." });
      return;
    }
    const at = new Date();
    setVisit({ ...FRESH_VISIT, saving: true });

    if (source === "prototype") {
      if (useCS) await wait(700);
      const canned = PROTOTYPE_PATIENTS.find((x) => x.patient.id === patient.id)?.analysis;
      const result: AnalysisResult | null = useCS && canned ? { ...canned, origin: "prototype" } : null;
      setVisit({ ...FRESH_VISIT, saved: true, result, checkedAt: hhmm(at) });
      return;
    }

    try {
      if (useCS) {
        const result = toAnalysis(await analyseNote({ patientId: patient.id, text, at }));
        setVisit({ ...FRESH_VISIT, saved: true, result, checkedAt: hhmm(at) });
      } else {
        await createNote({ patientId: patient.id, text, at });
        setVisit({ ...FRESH_VISIT, saved: true, checkedAt: hhmm(at) });
      }
      setNotes((n) => ({ ...n, [patient.id]: "" }));
      loadRecord(patient.id);
    } catch (e) {
      // A lost response can occur after commit; do not claim the note was not saved.
      setVisit({
        ...FRESH_VISIT,
        saveError: `Save could not be confirmed. Refresh patient history before retrying to avoid a duplicate note. ${message(e)}`,
        result: useCS ? { status: "unavailable", summary: "", findings: [], missing: [], error: message(e), origin: "backend" } : null,
      });
    }
  };

  const sendLocally = (notice = "") => {
    if (!patient || !res || (res.status !== "review" && res.status !== "urgent")) return;
    setSentItems((s) => ({
      ...s,
      [patient.id]: {
        key: `sent-${patient.id}`,
        name: patient.name,
        demo: patient.demo,
        time: hhmm(),
        from: NURSE,
        level: res.status === "urgent" ? "urgent" : "review",
        cs: true,
        summary: res.summary,
        findings: res.findings,
        missing: res.missing,
        origin: "local",
      },
    }));
    setVisit((v) => ({ ...v, blocked: false, sending: false, sendError: "", sendNotice: notice }));
  };

  const sendToPhysician = async () => {
    if (!patient || !res || (res.status !== "review" && res.status !== "urgent") || visit.sending) return;
    if (!(useBackendQueue && res.origin === "backend" && res.analysisId)) {
      sendLocally();
      return;
    }
    const patientId = patient.id;
    const analysisId = res.analysisId;
    setVisit((v) => ({ ...v, sending: true, sendError: "", sendNotice: "" }));
    try {
      // 201 = new request, 200 = already sent; both mean the physician has it.
      await createReviewRequest(patientId, analysisId, NURSE);
      setSentAnalyses((s) => ({ ...s, [patientId]: analysisId }));
      setVisit((v) => ({ ...v, sending: false, blocked: false }));
      refreshQueue();
    } catch (e) {
      setVisit((v) => ({ ...v, sending: false, sendError: `Physician submission could not be confirmed. Retrying this analysis is safe. ${message(e)}` }));
    }
  };

  const confirmDismiss = () => {
    if (!patient || !visit.reason) return;
    setDismissedFor((d) => ({ ...d, [patient.id]: visit.reason }));
    setVisit((v) => ({ ...v, choosing: false, blocked: false }));
  };

  const resetDemo = () => {
    if (visit.saving || visit.sending) return;
    setView("nurse");
    setUseCS(true);
    setSentItems({});
    // Saved review requests stay in the backend; only this browser forgets which ones it sent.
    setSentAnalyses({});
    setBackendQueue(null);
    setDismissedFor({});
    setDecisions({});
    setNotes({});
    setTab("notes");
    resetVisit();
    setPid(patientList[0]?.id ?? "");
  };

  const state: NurseState = {
    source,
    useCS,
    patients,
    patient,
    pid,
    record: patient ? (records[patient.id] ?? { status: "loading" }) : null,
    tab,
    note: noteText,
    saving: visit.saving,
    saved: visit.saved,
    saveError: visit.saveError,
    result: res,
    pending,
    unresolved,
    panelOpen,
    sent,
    sending: visit.sending,
    sendError: visit.sendError,
    sendNotice: visit.sendNotice,
    dismissed: dismissed ?? "",
    choosing: visit.choosing,
    reason: visit.reason,
    blocked: visit.blocked,
    checkedAt: visit.checkedAt,
  };

  return (
    <div className="flex min-h-screen flex-col bg-page text-ink">
      <DemoBar
        view={view}
        onView={setView}
        useCS={useCS}
        onToggleCS={() => {
          if (visit.saving || visit.sending) return;
          setUseCS((v) => !v);
          resetVisit();
        }}
        source={source}
        onSource={
          ALLOW_PROTOTYPE_DATASET
            ? (s) => {
                if (visit.saving || visit.sending) return;
                if (s !== source) {
                  resetDemo();
                  setSource(s);
                }
              }
            : undefined
        }
        onReset={resetDemo}
      />
      {view === "nurse" ? (
        <NurseView
          s={state}
          on={{
            pickPatient,
            tab: setTab,
            note: (text) => {
              if (!patient) return;
              setNotes((n) => ({ ...n, [patient.id]: text }));
              if (visit.saved || visit.saveError) resetVisit();
            },
            save,
            ack: () => setVisit((v) => ({ ...v, acked: true, closed: false })),
            close: () => setVisit((v) => ({ ...v, closed: true })),
            send: sendToPhysician,
            dismiss: () => setVisit((v) => ({ ...v, choosing: true })),
            reason: (reason) => setVisit((v) => ({ ...v, reason })),
            confirmDismiss,
            cancelDismiss: () => setVisit((v) => ({ ...v, choosing: false, reason: "" })),
            toDoctor: () => setView("doctor"),
            retry: () => setReloadKey((k) => k + 1),
            usePrototype: ALLOW_PROTOTYPE_DATASET ? () => setSource("prototype") : undefined,
          }}
        />
      ) : (
        <PhysicianView
          queue={queue}
          decisions={decisions}
          onDecide={(key, d) => setDecisions((x) => ({ ...x, [key]: d }))}
          loading={queueLoading}
          notice={queueNotice}
          onRefresh={useBackendQueue ? refreshQueue : undefined}
        />
      )}
    </div>
  );
}
