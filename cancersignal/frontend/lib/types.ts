// UI types. Components only use these; backend field names live in mappers.ts.

export type DataSource = "backend" | "prototype";

export type Patient = {
  id: string;
  name: string;
  /** e.g. "Female, 64" */
  demo: string;
  /** Appointment time, e.g. "08:45". */
  time: string;
  visit: string;
  /** Default text pre-filled in the note box (prototype only). */
  draftNote: string;
};

export type HistoryEntry = {
  /** Record id used for evidence matching (backend UUID or prototype ref). */
  id: string;
  /** Short human-readable reference shown next to the entry. */
  ref: string;
  date: string;
  kind: string;
  text: string;
  /** Sort key (ISO time or comparable string). */
  sortKey: string;
};

export type LabResult = {
  id: string;
  ref: string;
  date: string;
  test: string;
  value: string;
  /** Reference range; empty when the source does not provide one. */
  range: string;
  /** "L" / "H" only when the source provides it. Never computed in the UI. */
  flag: "" | "L" | "H";
  note: string;
};

export type Medication = { name: string; dose: string; status: string };

export type Referral = {
  date: string;
  title: string;
  detail: string;
  status: string;
  open: boolean;
};

export type PatientRecord = {
  history: HistoryEntry[];
  labs: LabResult[];
  meds: Medication[];
  refs: Referral[];
};

export type SourceRef = { id: string; label: string };

/** Priority set by the backend rule. The UI never decides it. */
export type FindingPriority = "urgent" | "review";

export type Finding = {
  id: string;
  title: string;
  detail: string;
  sources: SourceRef[];
  rule: string;
  ruleSrc: string;
  priority: FindingPriority;
};

export type AnalysisStatus = "none" | "review" | "urgent" | "unavailable";

export type AnalysisResult = {
  status: AnalysisStatus;
  summary: string;
  findings: Finding[];
  missing: string[];
  /** Readable reason when status is "unavailable". */
  error?: string;
  origin: DataSource;
};

export type QueueLevel = "urgent" | "review" | "normal";

export type QueueItem = {
  key: string;
  name: string;
  demo: string;
  time: string;
  from: string;
  level: QueueLevel;
  cs: boolean;
  summary: string;
  /** Full findings so the physician sees why the alert was raised (detail, sources, rule, priority). */
  findings: Finding[];
  /** "Not found in records" items from the analysis. */
  missing: string[];
};
