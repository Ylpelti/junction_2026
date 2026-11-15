// The ONLY place that knows backend field names. A backend change should only
// touch this file. Raw types mirror backend/app/schemas/{records,analysis}.py.

import type {
  AnalysisResult,
  ClinicalExplanation,
  Finding,
  FindingPriority,
  HistoryEntry,
  LabResult,
  Medication,
  Patient,
  PatientRecord,
  QueueItem,
  QueueLevel,
  QCancerEstimate,
  Referral,
} from "./types";

// ---- Raw API types -------------------------------------------------------

export type ApiPatient = {
  id: string;
  synthetic_name: string;
  birth_date: string;
  sex: "female" | "male" | "intersex" | "unknown";
  created_at: string;
};

export type ApiObservationType =
  | "clinical_note"
  | "symptom"
  | "laboratory"
  | "investigation"
  | "vital_sign"
  | "diagnosis"
  | "medication";

export type ApiObservation = {
  id: string;
  patient_id: string;
  encounter_id: string | null;
  observation_type: ApiObservationType;
  code: string | null;
  text: string | null;
  /** Decimal serialised as a string. */
  numeric_value: string | null;
  unit: string | null;
  status: string | null;
  observed_at: string;
  recorded_at: string;
};

type ApiEvidence = { observation_id: string; source_excerpt: string | null };

type ApiFinding = {
  id: string;
  finding_type: string;
  description: string;
  status: string;
  uncertainty: string | null;
  evidence: ApiEvidence[];
};

type ApiPrediction = {
  model_name: string;
  prediction_type: string;
  value: unknown;
  uncertainty: string | null;
};

type ApiTrigger = {
  id: string;
  trigger_rule_id?: string;
  rule_name: string;
  rule_version: string;
  demonstration_only: boolean;
  rule_source: string;
  rule_source_section: string;
  /** Set by the backend rule. Missing or unknown values count as "review". */
  priority?: "urgent" | "review";
  triggered: boolean;
  explanation: string;
  recommended_action: string | null;
  requires_clinician_review: boolean;
  evidence_observation_ids: string[];
};

export type ApiAnalysisResponse = {
  id: string;
  patient_id: string;
  created_at: string;
  status: "pending" | "running" | "completed" | "failed";
  findings: ApiFinding[];
  trigger_results: ApiTrigger[];
  predictions?: ApiPrediction[];
  source_observations: ApiObservation[];
  explanation: string;
  clinical_explanation?: ClinicalExplanation | null;
  provenance: {
    input_observation_id: string | null;
    cutoff: string | null;
    missing_information: string[];
    error_code: string | null;
  };
};

// ---- Helpers -------------------------------------------------------------

const SEX: Record<ApiPatient["sex"], string> = { female: "Female", male: "Male", intersex: "Intersex", unknown: "Sex unknown" };

const PREFIX: Record<ApiObservationType, string> = {
  clinical_note: "NOTE",
  symptom: "SYM",
  laboratory: "LAB",
  investigation: "INV",
  vital_sign: "VIT",
  diagnosis: "DX",
  medication: "MED",
};

const KIND: Record<ApiObservationType, string> = {
  clinical_note: "NOTE",
  symptom: "SYMPTOM",
  laboratory: "LAB",
  investigation: "INVESTIGATION",
  vital_sign: "VITAL SIGN",
  diagnosis: "DIAGNOSIS",
  medication: "MEDICATION",
};

/** Display-only age; no clinical logic depends on it. */
function ageOn(birthDate: string, today: Date): number | null {
  const [y, m, d] = birthDate.split("-").map(Number);
  if (!y || !m || !d) return null;
  let age = today.getFullYear() - y;
  if (today.getMonth() + 1 < m || (today.getMonth() + 1 === m && today.getDate() < d)) age -= 1;
  return age;
}

export function displayDate(iso: string): string {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : `${d.getDate()}.${d.getMonth() + 1}.${d.getFullYear()}`;
}

/** "132.000000" → "132"; formatting only, the value itself is unchanged. */
function displayDecimal(value: string): string {
  return value.includes(".") ? value.replace(/\.?0+$/, "") : value;
}

export function observationRef(o: Pick<ApiObservation, "id" | "observation_type">): string {
  return `${PREFIX[o.observation_type] ?? "REC"}-${o.id.slice(0, 8)}`;
}

function valueText(o: ApiObservation): string {
  return o.numeric_value === null ? "" : `${displayDecimal(o.numeric_value)}${o.unit ? ` ${o.unit}` : ""}`;
}

function isObj(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

// ---- Mappers -------------------------------------------------------------

export function toPatient(p: ApiPatient, appointment: { time: string; visit: string } | undefined, today = new Date()): Patient {
  const age = ageOn(p.birth_date, today);
  return {
    id: p.id,
    name: p.synthetic_name,
    demo: `${SEX[p.sex] ?? "Sex unknown"}${age === null ? "" : `, ${age}`}`,
    time: appointment?.time ?? "—",
    visit: appointment?.visit ?? "Not recorded",
    draftNote: "",
  };
}

export function toRecord(observations: ApiObservation[]): PatientRecord {
  const newestFirst = [...observations].sort((a, b) => b.observed_at.localeCompare(a.observed_at) || a.id.localeCompare(b.id));

  const history: HistoryEntry[] = newestFirst
    .filter((o) => o.observation_type !== "medication")
    .map((o) => {
      const value = valueText(o);
      const text =
        o.observation_type === "laboratory"
          ? [o.code, value].filter(Boolean).join(" ") + (o.text ? ` · ${o.text}` : "")
          : (o.text ?? value);
      return { id: o.id, ref: observationRef(o), date: displayDate(o.observed_at), kind: KIND[o.observation_type] ?? "RECORD", text, sortKey: o.observed_at };
    });

  // TODO(backend): no reference range or abnormal flag on lab observations; shown as "—", never computed here.
  const labs: LabResult[] = newestFirst
    .filter((o) => o.observation_type === "laboratory")
    .map((o) => ({
      id: o.id,
      ref: observationRef(o),
      date: displayDate(o.observed_at),
      test: o.code ?? "Unnamed test",
      value: valueText(o) || "—",
      range: "",
      flag: "",
      note: o.text ?? "",
    }));

  const meds: Medication[] = newestFirst
    .filter((o) => o.observation_type === "medication")
    .map((o) => ({ name: o.code ?? o.text ?? "Medication", dose: o.code ? (o.text ?? "") : "", status: o.status ?? "" }));

  // TODO(backend): no referral record type; investigation observations are the closest match.
  const refs: Referral[] = newestFirst
    .filter((o) => o.observation_type === "investigation")
    .map((o) => ({
      date: displayDate(o.observed_at),
      title: `Investigation${o.code ? `: ${o.code}` : ""}`,
      detail: o.text ?? "",
      status: o.status === "completed" ? "Completed" : o.status === "planned" ? "Planned" : (o.status ?? "Status unknown"),
      open: o.status !== "completed",
    }));

  return { history, labs, meds, refs, observations };
}

const ERROR_TEXT: Record<string, string> = {
  pipeline_execution_failed: "The analysis pipeline failed.",
};

function qcancerEstimate(predictions: ApiPrediction[] | undefined): QCancerEstimate | undefined {
  const prediction = predictions?.find((row) =>
    row.model_name === "QCancer-2013" && row.prediction_type === "current_undiagnosed_cancer_risk",
  );
  if (!prediction || !isObj(prediction.value)) return undefined;
  const value = prediction.value;
  const allowed = ["calculated", "insufficient_data", "invalid_input", "unsupported_input"] as const;
  if (typeof value.status !== "string" || !allowed.includes(value.status as (typeof allowed)[number])) return undefined;
  const risk = (candidate: unknown) => typeof candidate === "number" && Number.isFinite(candidate) ? candidate : null;
  return {
    status: value.status as QCancerEstimate["status"],
    horizonYears: typeof value.horizon_years === "number" ? value.horizon_years : 2,
    anyCancerRiskPercent: risk(value.any_cancer_risk_percent),
    colorectalCancerRiskPercent: risk(value.colorectal_cancer_risk_percent),
    missingInputs: Array.isArray(value.missing_inputs) ? value.missing_inputs.filter((x): x is string => typeof x === "string") : [],
    uncertainty: prediction.uncertainty,
  };
}

export function toAnalysis(r: ApiAnalysisResponse): AnalysisResult {
  const missing = [...(r.provenance.missing_information ?? [])];
  const qcancer = qcancerEstimate(r.predictions);

  if (r.status !== "completed" || r.provenance.error_code) {
    const code = r.provenance.error_code;
    return {
      status: "unavailable",
      summary: r.explanation,
      findings: [],
      missing,
      error:
        (r.status === "failed" || code)
          ? `Analysis failed${code ? ` (${ERROR_TEXT[code] ?? code})` : ""}.`
          : "Analysis has not completed.",
      origin: "backend",
      analysisId: r.id,
    };
  }

  const sources = new Map(r.source_observations.map((o) => [o.id, o]));
  const label = (id: string): string | null => {
    if (id === r.provenance.input_observation_id) return "Today";
    const o = sources.get(id);
    return o ? observationRef(o) : null;
  };

  // The rule decides urgency; anything other than "urgent" is review (backwards compatible).
  const priorityOf = (t: ApiTrigger): FindingPriority => (t.priority === "urgent" ? "urgent" : "review");

  let hidden = 0;
  const findings: Finding[] = r.trigger_results
    .filter((t) => t.triggered)
    // Urgent first, otherwise keep the backend's rule order (sort is stable).
    .sort((a, b) => Number(priorityOf(b) === "urgent") - Number(priorityOf(a) === "urgent"))
    .map((t, index) => {
      const ids = new Set(t.evidence_observation_ids);
      const support = r.findings.filter((f) => f.evidence.some((e) => ids.has(e.observation_id)));
      const chips = t.evidence_observation_ids.flatMap((id) => {
        const l = label(id);
        if (l === null) {
          hidden += 1; // Unverifiable reference: never shown.
          return [];
        }
        return [{ id, label: l }];
      });
      return {
        id: `F${index + 1}`,
        title: t.rule_name,
        detail: [t.explanation, ...support.map((f) => f.description)].join(" "),
        sources: chips,
        rule: `${t.rule_name} (${t.rule_version}${t.demonstration_only ? ", demonstration rule" : ""})`,
        ruleSrc: [t.rule_source, t.rule_source_section].filter(Boolean).join(" "),
        priority: priorityOf(t),
      };
    });

  if (hidden > 0) missing.push(`${hidden} evidence reference(s) could not be resolved to a source record and are not shown.`);

  return {
    status: findings.some((f) => f.priority === "urgent") ? "urgent" : findings.length > 0 ? "review" : "none",
    summary: r.explanation,
    clinicalExplanation: r.clinical_explanation?.contract_version === "2.0" && r.clinical_explanation.language === "en" ? r.clinical_explanation : undefined,
    findings,
    qcancer,
    missing,
    origin: "backend",
    analysisId: r.id,
    triggeredRuleIds: r.trigger_results.filter(t => t.triggered).flatMap(t => t.trigger_rule_id ? [t.trigger_rule_id] : []),
    sourceObservations: r.source_observations,
    clinicalFindings: r.findings,
  };
}

// ---- Physician review requests (docs/physician-review-api.md) -------------

export type ApiReviewRequest = {
  id: string;
  patient_id: string;
  analysis_id: string;
  status: "pending" | "reviewed";
  /** Snapshotted by the backend from triggered rule priorities; never set by the client. */
  priority: "urgent" | "review" | "normal";
  created_at: string;
  submitted_by: string | null;
  patient: ApiPatient;
  analysis: ApiAnalysisResponse;
};

function receivedAt(iso: string, today = new Date()): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const time = `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
  const sameDay = d.toDateString() === today.toDateString();
  return sameDay ? time : `${displayDate(iso)} ${time}`;
}

export function toQueueItem(r: ApiReviewRequest): QueueItem {
  const analysis = toAnalysis(r.analysis);
  const level: QueueLevel = r.priority === "urgent" ? "urgent" : r.priority === "review" ? "review" : "normal";
  return {
    key: r.id,
    status: r.status,
    analysisId: r.analysis_id,
    patientId: r.patient_id,
    analysis,
    name: r.patient.synthetic_name,
    demo: toPatient(r.patient, undefined).demo,
    time: receivedAt(r.created_at),
    from: r.submitted_by ?? "Not recorded",
    level,
    cs: level !== "normal",
    summary: r.analysis.clinical_explanation?.summary_en || r.analysis.explanation,
    clinicalExplanation: analysis.clinicalExplanation,
    findings: analysis.findings,
    missing: analysis.missing,
    origin: "backend",
  };
}
