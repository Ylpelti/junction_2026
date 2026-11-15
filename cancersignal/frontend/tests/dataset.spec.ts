import { test, expect, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";
import { CANONICAL_PATIENT_IDS } from "../lib/demo-dataset";
import { listPatients, listReviewRequests, listAnalyses, ApiError } from "../lib/api";
import { formatDecimal, formatMeasurement } from "../lib/format";
import { toQueueItem } from "../lib/mappers";
import { patient, second, run, review, observation } from "./fixtures";
import { ClinicalExplanationCard } from "../components/ClinicalExplanationCard";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
const legacy = { ...patient, id: "9e6f8a99-3d15-57b6-9fe3-26385fc9e641", synthetic_name: "SYNTHETIC Nieminen Pertti" };
const legacyReview = { ...review, id: "188229ec-b634-4585-b54d-46404d6957ae", patient_id: legacy.id, patient: legacy, analysis_id: "10338d63-e686-45d8-b8de-287633bdcdcc", analysis: { ...run, id: "10338d63-e686-45d8-b8de-287633bdcdcc", patient_id: legacy.id, explanation: "CANNED_FIT_48", source_observations: [{ ...observation, patient_id: legacy.id, code: "F-HB-FIT", numeric_value: "48.000000", unit: "ug/g" }] } };
const originalFetch = globalThis.fetch;
const response = (body: unknown) => new Response(JSON.stringify(body));
test.afterEach(() => { globalThis.fetch = originalFetch; });

test("canonical UUID registry matches the seed exactly, with no clinical fixture payload", () => {
  const seed = JSON.parse(readFileSync("../backend/app/db/demo_data/patients.en-v2.json", "utf8"));
  expect([...CANONICAL_PATIENT_IDS].sort()).toEqual(seed.patients.map((p: { id: string }) => p.id).sort());
  expect(CANONICAL_PATIENT_IDS).toHaveLength(4);
});
test("mixed API dataset excludes legacy and prototype IDs without replacing findings", async () => {
  globalThis.fetch = async () => response([legacy, patient, { ...legacy, id: "CS-4501" }]);
  expect(await listPatients()).toEqual([patient]);
  globalThis.fetch = async () => response([legacyReview, review]);
  expect(await listReviewRequests()).toEqual([review]);
  expect(toQueueItem(review).analysis?.sourceObservations).toEqual(run.source_observations);
  expect(toQueueItem(review).level).toBe(review.priority);
});
test("mock queue IDs and mismatched source-patient relationships fail closed", async () => {
  globalThis.fetch = async () => response([{ ...review, id: "q1" }]);
  await expect(listReviewRequests()).rejects.toBeInstanceOf(ApiError);
  globalThis.fetch = async () => response([{ ...review, analysis: { ...run, source_observations: [{ ...observation, patient_id: legacy.id }] } }]);
  await expect(listReviewRequests()).rejects.toThrow("source-patient");
  globalThis.fetch = async () => response([{ ...run, patient_id: second.id }]);
  await expect(listAnalyses(patient.id)).rejects.toThrow("source-patient");
});
test("rule explanation joins use actual triggered rule UUIDs and never non-triggered prose", () => {
  const value = { ...run.clinical_explanation!, rule_results: [
    { key: "matched", text_en: "Matched rule", observation_ids: [observation.id], rule_reference: { trigger_rule_id: "matched-rule" } },
    { key: "not-matched", text_en: "Stored rule did not match the supplied information.", observation_ids: [], rule_reference: { trigger_rule_id: "not-matched-rule" } },
  ] };
  const html = renderToStaticMarkup(createElement(ClinicalExplanationCard, { value, triggeredRuleIds: ["matched-rule"] }));
  expect(html).toContain("Matched rule"); expect(html).not.toContain("did not match");
  expect(html).toContain("Source details"); expect(html).toContain(observation.id);
});
test("measurement formatting is exact and does not round or convert units", () => {
  expect(formatMeasurement("48.000000", "ug/g")).toBe("48 µg/g");
  expect(formatMeasurement("113.000000", "g/L")).toBe("113 g/L");
  expect(formatDecimal("0.0000012300")).toBe("0.00000123");
  expect(formatDecimal("9007199254740993.0100")).toBe("9007199254740993.01");
  expect(observation.numeric_value).toBe("110");
});

async function mixedBackend(page: Page, fit = false) {
  const canonicalRun = { ...run, source_observations: [{ ...observation, numeric_value: fit ? "48.000000" : "110.000000", code: fit ? "F-HB-FIT" : "B-Hb", unit: fit ? "ug/g" : "g/L" }], clinical_explanation: { ...run.clinical_explanation!, limitations: [{ code: "technical", text_en: "VALIDATION_WARNING" }], rule_results: [{ key: "not-matched", text_en: "Stored rule did not match the supplied information.", observation_ids: [] }] } };
  let posts = 0;
  await page.route("**/api/v1/**", async route => {
    const req = route.request(); const url = new URL(req.url());
    if (req.method() === "POST") { posts++; return route.fulfill({ status: 500, body: "{}" }); }
    let body: unknown = [];
    if (url.pathname.endsWith("/patients")) body = [legacy, patient, second, { ...legacy, id: "CS-4501" }];
    if (url.pathname.endsWith("/analyses")) body = url.pathname.includes(patient.id) ? [canonicalRun] : [];
    if (url.pathname.endsWith("/observations")) body = url.pathname.includes(patient.id) ? canonicalRun.source_observations : [];
    if (url.pathname.endsWith("/dismissal")) return route.fulfill({ status: 404, body: "{}" });
    if (url.pathname.endsWith("/review-requests")) body = url.searchParams.get("status") === "reviewed" ? [] : [legacyReview, { ...review, analysis: canonicalRun }].filter(r => !url.searchParams.has("patient_id") || url.searchParams.get("patient_id") === r.patient_id);
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(body) });
  });
  return () => posts;
}
test("backend mode never displays prototype patients, mock queue entries or canned FIT across mode switches", async ({ page }) => {
  const posts = await mixedBackend(page); await page.goto("/");
  await expect(page.getByRole("button", { name: /SYNTHETIC Laine/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Nieminen Pertti/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Physician view", exact: true }).click();
  await expect(page.locator("ol > li")).toHaveCount(1);
  for (const forbidden of [/Nieminen Pertti/, /Lehtonen Juha/, /Salminen Emma/, /CANNED_FIT_48/, /48 µg/]) await expect(page.getByText(forbidden)).toHaveCount(0);
  await expect(page.locator("ol > li").first()).toContainText("English clinical summary");
  await expect(page.getByText("VALIDATION_WARNING")).not.toBeVisible();
  await expect(page.getByText("Stored rule did not match the supplied information.")).toHaveCount(0);
  await page.getByRole("button", { name: "Prototype data", exact: true }).click();
  await expect(page.getByText(/Prototype only · canned/)).toBeVisible();
  await expect(page.getByText("Lehtonen Juha", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Backend data", exact: true }).click();
  await expect(page.locator("ol > li")).toHaveCount(1);
  await expect(page.getByText(/Lehtonen Juha|Salminen Emma|Nieminen Pertti/)).toHaveCount(0);
  await page.getByRole("button", { name: "With CancerSignal", exact: true }).click();
  await expect(page.getByText(/Lehtonen Juha|Salminen Emma|Nieminen Pertti/)).toHaveCount(0);
  expect(posts()).toBe(0);
});
test("a recorded completed FIT is visible and generic actions do not recommend repeating it", async ({ page }) => {
  await mixedBackend(page, true); await page.goto("/");
  await page.getByRole("button", { name: "Physician view", exact: true }).click();
  await expect(page.getByRole("region", { name: "Completed tests" })).toContainText("48 µg/g");
  await expect(page.getByRole("button", { name: /Simulate FIT order/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: /Simulate repeat FIT/ })).not.toBeVisible();
  await page.getByText("Record a simulated decision", { exact: true }).click();
  await expect(page.getByRole("button", { name: "Simulate repeat FIT (clinician choice)" })).toBeVisible();
  await expect(page.getByText(/not recommendations/)).toBeVisible();
});
