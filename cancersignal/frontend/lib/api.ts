// One function per backend endpoint used by the UI. Responses are validated
// lightly here and mapped to UI types in mappers.ts.

import type {
  ApiAnalysisResponse,
  ApiObservation,
  ApiPatient,
  ApiReviewRequest,
} from "./mappers";

const BASE = `${(process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(/\/$/, "")}/api/v1`;

export const API_ORIGIN = BASE.replace(/\/api\/v1$/, "");

export class ApiError extends Error {
  /** HTTP status, or undefined when the backend could not be reached at all. */
  readonly status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.status = status;
  }

  get unreachable() {
    return this.status === undefined;
  }
}

async function request<T>(path: string, init?: RequestInit, check?: (body: unknown) => boolean): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: init?.body ? { "Content-Type": "application/json" } : undefined,
      cache: "no-store",
    });
  } catch {
    throw new ApiError(`Cannot reach the backend at ${API_ORIGIN}. Is it running, and does it allow this origin (CORS)?`);
  }
  let body: unknown = null;
  try {
    body = await response.json();
  } catch {
    // Non-JSON body; handled below.
  }
  if (!response.ok) {
    throw new ApiError(`Backend returned ${response.status}: ${describeDetail(body)}`, response.status);
  }
  if (check && !check(body)) {
    throw new ApiError(`Unexpected response shape from ${path}.`, response.status);
  }
  return body as T;
}

function describeDetail(body: unknown): string {
  if (body && typeof body === "object" && "detail" in body) {
    const detail = (body as { detail: unknown }).detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail
        .map((d) => (d && typeof d === "object" && "msg" in d ? String((d as { msg: unknown }).msg) : "invalid input"))
        .join("; ");
    }
  }
  return "request failed";
}

const isObj = (v: unknown): v is Record<string, unknown> => !!v && typeof v === "object" && !Array.isArray(v);
const isPatient = (v: unknown) => isObj(v) && typeof v.id === "string" && typeof v.synthetic_name === "string";
const isObservation = (v: unknown) =>
  isObj(v) && typeof v.id === "string" && typeof v.observation_type === "string" && typeof v.observed_at === "string";
const listOf = (item: (v: unknown) => boolean) => (v: unknown) => Array.isArray(v) && v.every(item);
const isAnalysis = (v: unknown) =>
  isObj(v) &&
  typeof v.id === "string" &&
  typeof v.status === "string" &&
  Array.isArray(v.findings) &&
  Array.isArray(v.trigger_results) &&
  Array.isArray(v.source_observations) &&
  isObj(v.provenance);

/** GET /patients */
export function listPatients() {
  return pages<ApiPatient>("/patients?", isPatient);
}

/** GET /patients/{id}/observations (all types; split in the mapper). */
export async function listObservations(patientId: string) {
  const rows: ApiObservation[] = [];
  for (let offset = 0; ; offset += 200) {
    const page = await request<ApiObservation[]>(
      `/patients/${encodeURIComponent(patientId)}/observations?limit=200&offset=${offset}`,
      undefined, listOf(isObservation),
    );
    rows.push(...page);
    if (page.length < 200) return rows;
  }
}

type NewNote = { patientId: string; text: string; at: Date };

function notePayload({ patientId, text, at }: NewNote) {
  const t = at.toISOString();
  return { patient_id: patientId, observation_type: "clinical_note", text, observed_at: t, recorded_at: t };
}

/** POST /patients/{id}/observations: save a note without analysis ("current practice"). */
export function createNote(note: NewNote) {
  return request<ApiObservation>(
    `/patients/${encodeURIComponent(note.patientId)}/observations`,
    { method: "POST", body: JSON.stringify(notePayload(note)) },
    isObservation,
  );
}

/** POST /patients/{id}/analyses: saves the note and runs the pipeline with cutoff = save time. */
export function analyseNote(note: NewNote) {
  return request<ApiAnalysisResponse>(
    `/patients/${encodeURIComponent(note.patientId)}/analyses`,
    { method: "POST", body: JSON.stringify({ note: notePayload(note) }) },
    isAnalysis,
  );
}

const isReviewRequest = (v: unknown) =>
  isObj(v) &&
  typeof v.id === "string" &&
  typeof v.analysis_id === "string" &&
  (v.priority === "urgent" || v.priority === "review" || v.priority === "normal") &&
  isPatient(v.patient) &&
  isAnalysis(v.analysis);

/**
 * POST /patients/{id}/review-requests. 201 = new request, 200 = this analysis was
 * already sent (the original request is returned). Both are success.
 */
export function createReviewRequest(patientId: string, analysisId: string, submittedBy: string) {
  return request<ApiReviewRequest>(
    `/patients/${encodeURIComponent(patientId)}/review-requests`,
    { method: "POST", body: JSON.stringify({ analysis_id: analysisId, submitted_by: submittedBy }) },
    isReviewRequest,
  );
}

/** GET /review-requests: pending queue, already ordered urgent → review → normal, oldest first. */
export function listReviewRequests(status: "pending" | "reviewed" | "all" = "pending", patientId?: string) {
  return pages<ApiReviewRequest>(`/review-requests?status=${status}&${patientId ? `patient_id=${encodeURIComponent(patientId)}&` : ""}`, isReviewRequest);
}

/** GET /review-requests/{id} */
export function getReviewRequest(id: string) {
  return request<ApiReviewRequest>(`/review-requests/${encodeURIComponent(id)}`, undefined, isReviewRequest);
}

async function pages<T>(path: string, check: (v: unknown) => boolean): Promise<T[]> {
  const rows: T[] = [];
  for (let offset = 0; ; offset += 200) {
    const page = await request<T[]>(`${path}limit=200&offset=${offset}`, undefined, listOf(check));
    rows.push(...page);
    if (page.length < 200) return rows;
  }
}

export function listAnalyses(patientId: string) {
  return pages<ApiAnalysisResponse>(`/patients/${encodeURIComponent(patientId)}/analyses?`, isAnalysis);
}
export function analyseSavedNote(patientId: string, noteId: string) {
  return request<ApiAnalysisResponse>(`/patients/${encodeURIComponent(patientId)}/analyses`,
    { method: "POST", body: JSON.stringify({ note_observation_id: noteId }) }, isAnalysis);
}

export const DISMISSAL_REASONS = {
  already_aware: "Physician already aware or investigation under way",
  another_diagnosis: "Symptoms explained by another diagnosis",
  patient_declined: "Patient declined further investigation",
  other: "Other (explained in the record)",
} as const;
export const DECISION_ACTIONS = {
  fit_ordered: "FIT ordered", referral_made: "Referral made", no_action: "No action", acknowledged: "Acknowledged",
} as const;
export type DismissalReason = keyof typeof DISMISSAL_REASONS;
export type DecisionAction = keyof typeof DECISION_ACTIONS;
export type Dismissal = { id: string; analysis_id: string; patient_id: string; reason_code: DismissalReason; actor: string; comment: string | null; created_at: string };
export type Decision = { id: string; review_request_id: string; action: DecisionAction; actor: string; comment: string | null; created_at: string; status: "reviewed" };
const isDismissal = (v: unknown) => isObj(v) && typeof v.id === "string" && typeof v.analysis_id === "string" && typeof v.patient_id === "string" && typeof v.created_at === "string" && typeof v.actor === "string" && typeof v.reason_code === "string" && Object.hasOwn(DISMISSAL_REASONS, v.reason_code);
const isDecision = (v: unknown) => isObj(v) && typeof v.id === "string" && typeof v.review_request_id === "string" && v.status === "reviewed" && typeof v.created_at === "string" && typeof v.actor === "string" && typeof v.action === "string" && Object.hasOwn(DECISION_ACTIONS, v.action);
async function optional<T>(path: string, check: (v: unknown) => boolean): Promise<T | null> {
  try { return await request<T>(path, undefined, check); }
  catch (e) { if (e instanceof ApiError && e.status === 404) return null; throw e; }
}
export const getDismissal = (id: string) => optional<Dismissal>(`/analyses/${encodeURIComponent(id)}/dismissal`, isDismissal);
export const getDecision = (id: string) => optional<Decision>(`/review-requests/${encodeURIComponent(id)}/decision`, isDecision);

// A POST may have committed even when its response was lost. Always read back;
// return the actual saved action, which may differ from the attempted action.
async function persist<T>(path: string, body: unknown, check: (v: unknown) => boolean, read: () => Promise<T | null>): Promise<T> {
  try { return await request<T>(path, { method: "POST", body: JSON.stringify(body) }, check); }
  catch (error) {
    const saved = await read();
    if (saved) return saved;
    throw error;
  }
}
export const saveDismissal = (id: string, patientId: string, reason: DismissalReason) => persist<Dismissal>(
  `/analyses/${encodeURIComponent(id)}/dismissal`, { patient_id: patientId, reason_code: reason, actor: "SYNTHETIC Nurse H. Virtanen" }, isDismissal, () => getDismissal(id));
export const saveDecision = (id: string, action: DecisionAction) => persist<Decision>(
  `/review-requests/${encodeURIComponent(id)}/decision`, { action, actor: "SYNTHETIC Physician M. Salo" }, isDecision, () => getDecision(id));
