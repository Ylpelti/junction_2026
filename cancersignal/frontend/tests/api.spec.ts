import { test, expect } from "@playwright/test";
import { ApiError, listObservations, listReviewRequests, listPatients, getDismissal, saveDismissal, saveDecision, analyseSavedNote } from "../lib/api";
import { toAnalysis, toRecord, toQueueItem, type ApiAnalysisResponse } from "../lib/mappers";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { ClinicalExplanationCard } from "../components/ClinicalExplanationCard";
import { QCancerEstimateCard } from "../components/FindingsPanel";
import { run, observation, patient, review } from "./fixtures";
const originalFetch = globalThis.fetch;
test.afterEach(() => { globalThis.fetch = originalFetch; });
const response = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });

test("observations load every page and retain source metadata", async () => {
  const offsets: string[] = [];
  globalThis.fetch = async url => { offsets.push(String(url)); return response(offsets.length === 1 ? Array.from({ length: 200 }, (_, i) => ({ ...observation, id: String(i) })) : [{ ...observation, id: "last" }]); };
  const rows = await listObservations(patient.id);
  expect(rows).toHaveLength(201); expect(offsets[1]).toContain("offset=200");
  expect(toRecord(rows).observations?.[200]).toEqual({ ...observation, id: "last" });
});
test("patients and reviews page without reordering and use status=all", async () => {
  let count = 0;
  globalThis.fetch = async url => { expect(String(url)).toContain("status=all"); expect(String(url)).toContain(`patient_id=${patient.id}`); return response(++count === 1 ? Array(200).fill(review) : [{ ...review, id: "last", status: "reviewed" }]); };
  expect((await listReviewRequests("all", patient.id)).at(-1)?.id).toBe("last");
  globalThis.fetch = async () => response([patient]); expect(await listPatients()).toEqual([patient]);
});
test("only a dismissal GET 404 means absent", async () => {
  globalThis.fetch = async () => response({ detail: "missing" }, 404); expect(await getDismissal(run.id)).toBeNull();
  globalThis.fetch = async () => response({ detail: "unavailable" }, 503); await expect(getDismissal(run.id)).rejects.toBeInstanceOf(ApiError);
});
test("dismissal conflict reads actual reason, actor and server timestamp", async () => {
  const saved = { id: "d", analysis_id: run.id, patient_id: patient.id, reason_code: "patient_declined", actor: "SYNTHETIC other nurse", created_at: "2026-11-14T09:00:00Z", comment: null };
  globalThis.fetch = async (url, init) => { expect(String(url)).toContain(`/analyses/${run.id}/dismissal`); if (init?.method === "POST") { expect(JSON.parse(init.body as string).reason_code).toBe("already_aware"); return response({}, 409); } return response(saved); };
  expect(await saveDismissal(run.id, patient.id, "already_aware")).toEqual(saved);
});
test("lost decision response reconciles against request UUID", async () => {
  const saved = { id: "d", review_request_id: review.id, action: "no_action", actor: "SYNTHETIC doctor", status: "reviewed", created_at: "2026-11-14T09:00:00Z" };
  globalThis.fetch = async (url, init) => { expect(String(url)).toContain(`/review-requests/${review.id}/decision`); if (init?.method === "POST") throw new TypeError("network"); return response(saved); };
  expect((await saveDecision(review.id, "fit_ordered")).action).toBe("no_action");
});
test("network failure without saved action never claims success", async () => {
  globalThis.fetch = async (_, init) => { if (init?.method === "POST") throw new TypeError("network"); return response({}, 404); };
  await expect(saveDecision(review.id, "fit_ordered")).rejects.toBeInstanceOf(ApiError);
});
test("saved-note analysis sends the observation UUID without new note text", async () => {
  globalThis.fetch = async (_, init) => { expect(JSON.parse(init!.body as string)).toEqual({ note_observation_id: observation.id }); return response(run); };
  expect((await analyseSavedNote(patient.id, observation.id)).id).toBe(run.id);
});
test("mapper uses rule priority, retains explanation, and preserves insufficient-data QCancer", () => {
  const result = toAnalysis(run);
  expect(result.status).toBe("review"); expect(result.analysisId).toBe(run.id);
  expect(result.qcancer?.status).toBe("insufficient_data"); expect(result.qcancer?.anyCancerRiskPercent).toBeNull();
  expect(result.sourceObservations).toEqual([observation]);
  expect(toAnalysis({ ...run, status: "failed" }).status).toBe("unavailable");
  expect(toAnalysis({ ...run, provenance: { ...run.provenance, error_code: "failure" } }).status).toBe("unavailable");
  expect(toQueueItem({ ...review, status: "reviewed" }).status).toBe("reviewed");
});
test("Finnish explanation and missing research inputs render without invented scores", () => {
  const result = toAnalysis(run);
  const explanation = renderToStaticMarkup(createElement(ClinicalExplanationCard, { value: result.clinicalExplanation! }));
  expect(explanation).toContain("Suomenkielinen yhteenveto"); expect(explanation).toContain(observation.id);
  const model = renderToStaticMarkup(createElement(QCancerEstimateCard, { estimate: result.qcancer! }));
  expect(model).toContain("smoking"); expect(model).not.toContain("0%");
});
