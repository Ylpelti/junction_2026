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
  observations?: import("./mappers").ApiObservation[];
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

export type QCancerEstimate = {
  status: "calculated" | "insufficient_data" | "invalid_input" | "unsupported_input";
  horizonYears: number;
  anyCancerRiskPercent: number | null;
  colorectalCancerRiskPercent: number | null;
  missingInputs: string[];
  uncertainty: string | null;
};

export type ExplanationStatement = {
  key: string; text_en: string; observation_ids: string[];
  rule_reference?: { trigger_rule_id: string } | null;
  requires_clinician_review?: boolean | null;
};
export type ClinicalExplanation = {
  contract_version: "2.0";
  language: "en";
  issues?: { code: string; message: string }[];
  provenance?: { name: string; method: string; version: string };
  mode: "llm" | "fallback" | "unavailable";
  summary_en: string;
  findings: ExplanationStatement[];
  mathematical_outputs: ExplanationStatement[];
  rule_results: ExplanationStatement[];
  limitations: { code: string; text_en: string }[];
};

export type AnalysisResult = {
  status: AnalysisStatus;
  summary: string;
  clinicalExplanation?: ClinicalExplanation;
  findings: Finding[];
  qcancer?: QCancerEstimate;
  missing: string[];
  /** Readable reason when status is "unavailable". */
  error?: string;
  origin: DataSource;
  /** Saved backend analysis id; needed to send a physician review request. */
  analysisId?: string;
  triggeredRuleIds?: string[];
  sourceObservations?: import("./mappers").ApiObservation[];
  clinicalFindings?: { id: string; description: string; status: string; uncertainty: string | null }[];
};

export type QueueLevel = "urgent" | "review" | "normal";

export type QueueItem = {
  key: string;
  status?: "pending" | "reviewed";
  analysisId?: string;
  patientId?: string;
  observations?: import("./mappers").ApiObservation[];
  analysis?: AnalysisResult;
  name: string;
  demo: string;
  time: string;
  from: string;
  level: QueueLevel;
  cs: boolean;
  summary: string;
  clinicalExplanation?: ClinicalExplanation;
  /** Full findings so the physician sees why the alert was raised (detail, sources, rule, priority). */
  findings: Finding[];
  /** "Not found in records" items from the analysis. */
  missing: string[];
  /** "backend" = saved review request; "demo" = fallback data; "local" = browser-only send. */
  origin?: "backend" | "demo" | "local";
};
