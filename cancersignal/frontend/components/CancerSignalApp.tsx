"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { FALLBACK_APPOINTMENTS, FALLBACK_QUEUE, PROTOTYPE_PATIENTS } from "../data/fallback";
import { analyseNote, ApiError, createNote, listObservations, listPatients } from "../lib/api";
import { ALLOW_PROTOTYPE_DATASET, USE_FALLBACK_APPOINTMENTS, USE_FALLBACK_QUEUE, USE_LOCAL_WORKFLOW } from "../lib/flags";
import { toAnalysis, toPatient, toRecord } from "../lib/mappers";
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
};

const FRESH_VISIT: Visit = {
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
  // TODO(backend): no endpoints for send/dismiss/queue/decisions; client state while USE_LOCAL_WORKFLOW is on.
  const [sentItems, setSentItems] = useState<Record<string, QueueItem>>({});
  const [dismissedFor, setDismissedFor] = useState<Record<string, string>>({});
  const [decisions, setDecisions] = useState<Record<string, string>>({});
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
  const sent = !!sentItems[pid];
  const dismissed = dismissedFor[pid];
  const unresolved = flagged && !sent && !dismissed;
  const panelOpen = flagged && visit.acked && !visit.closed;

  const queue = useMemo(() => {
    const rank = { urgent: 0, review: 1, normal: 2 } as const;
    const items = [
      ...(USE_FALLBACK_QUEUE ? FALLBACK_QUEUE.filter((x) => useCS || !x.cs) : []),
      ...(useCS && USE_LOCAL_WORKFLOW ? Object.values(sentItems) : []),
    ];
    return items.sort((a, b) => rank[a.level] - rank[b.level] || a.time.localeCompare(b.time));
  }, [sentItems, useCS]);

  // ---- Actions -----------------------------------------------------------

  const resetVisit = () => setVisit(FRESH_VISIT);

  const pickPatient = (id: string) => {
    if (id === pid) return;
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
    setVisit({ ...FRESH_VISIT, saving: useCS });

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
      // Request failed: the note was not saved. Never hide this behind silence.
      setVisit({
        ...FRESH_VISIT,
        saveError: `Note not saved. ${message(e)}`,
        result: useCS ? { status: "unavailable", summary: "", findings: [], missing: [], error: message(e), origin: "backend" } : null,
      });
    }
  };

  const sendToPhysician = () => {
    if (!patient || !res || (res.status !== "review" && res.status !== "urgent")) return;
    setSentItems((s) => ({
      ...s,
      [patient.id]: {
        key: `sent-${patient.id}`,
        name: patient.name,
        demo: patient.demo,
        time: hhmm(),
        from: "Nurse H. Virtanen",
        level: res.status === "urgent" ? "urgent" : "review",
        cs: true,
        summary: res.summary,
        findings: res.findings.map(({ id, title, rule, ruleSrc }) => ({ id, title, rule, ruleSrc })),
      },
    }));
    setVisit((v) => ({ ...v, blocked: false }));
  };

  const confirmDismiss = () => {
    if (!patient || !visit.reason) return;
    setDismissedFor((d) => ({ ...d, [patient.id]: visit.reason }));
    setVisit((v) => ({ ...v, choosing: false, blocked: false }));
  };

  const resetDemo = () => {
    setView("nurse");
    setUseCS(true);
    setSentItems({});
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
          setUseCS((v) => !v);
          resetVisit();
        }}
        source={source}
        onSource={
          ALLOW_PROTOTYPE_DATASET
            ? (s) => {
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
        <PhysicianView queue={queue} decisions={decisions} onDecide={(key, d) => setDecisions((x) => ({ ...x, [key]: d }))} />
      )}
    </div>
  );
}
