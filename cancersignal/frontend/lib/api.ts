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
  return request<ApiPatient[]>("/patients?limit=200", undefined, listOf(isPatient));
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
export function listReviewRequests() {
  return request<ApiReviewRequest[]>("/review-requests?status=pending&limit=200", undefined, listOf(isReviewRequest));
}

/** GET /review-requests/{id} */
export function getReviewRequest(id: string) {
  return request<ApiReviewRequest>(`/review-requests/${encodeURIComponent(id)}`, undefined, isReviewRequest);
}
