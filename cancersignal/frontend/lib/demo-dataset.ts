// Dataset membership only. IDs come from backend/app/db/demo_data/patients.json.
// Never put clinical fixture content, expected findings or priorities here.
// Regression tests verify this registry against the canonical source fixture.
export const CANONICAL_PATIENT_IDS: readonly string[] = [
  "138fff92-bea8-5f85-a95a-5fb502fd9e57",
  "9f1864d7-0a2b-55d2-a007-7f886ab65b2e",
  "53bcac07-8145-5a0a-bcf9-a64720ceecac",
  "6fa564bb-9001-5226-b01e-2fbb61cc4526"
];
export const isCanonicalPatient = (id: string) => CANONICAL_PATIENT_IDS.includes(id);
export const isUuid = (id: unknown): id is string => typeof id === "string" && /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id);
