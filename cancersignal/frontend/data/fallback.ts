// Local data taken from docs/design/Main.dc.html (synthetic, fictional).
// Used only for gaps in the backend API; see lib/flags.ts.

import type { AnalysisResult, Patient, PatientRecord, QueueItem } from "../lib/types";

// TODO(backend): appointment time and reason for visit have no endpoint.
// Applied to backend patients by list order while USE_FALLBACK_APPOINTMENTS is on.
export const FALLBACK_APPOINTMENTS: { time: string; visit: string }[] = [
  { time: "08:15", visit: "Stomach bug" },
  { time: "08:45", visit: "Fatigue" },
  { time: "09:30", visit: "Abdominal complaints" },
  { time: "10:00", visit: "Fatigue" },
  { time: "10:30", visit: "Follow-up" },
  { time: "11:00", visit: "Abdominal complaints" },
  { time: "11:30", visit: "Routine check" },
  { time: "13:00", visit: "Fatigue" },
];

// TODO(backend): no physician queue endpoint. Items other nurses sent earlier today.
export const FALLBACK_QUEUE: QueueItem[] = [
  {
    key: "q1",
    name: "Mäkelä Ritva",
    demo: "Female, 77",
    time: "07:50",
    from: "Nurse K. Lind",
    level: "review",
    cs: true,
    summary: "Iron-deficiency anaemia on 2.10. at age 77; no follow-up recorded in the following five weeks.",
    findings: [
      {
        id: "F1",
        title: "Iron-deficiency anaemia, unresolved",
        detail: "Low Hb and ferritin on 2.10. at age 77. No repeat Hb, FIT or investigation recorded in the following five weeks.",
        sources: [
          { id: "LAB-1002", label: "LAB-1002" },
          { id: "NOTE-1002", label: "NOTE-1002" },
        ],
        rule: "SUO-03",
        ruleSrc: "NICE DG56/HTG690 1.1: offer FIT",
        priority: "review",
      },
    ],
    missing: ["No FIT (faecal immunochemical test) result", "No follow-up Hb after 2.10."],
  },
  {
    key: "q2",
    name: "Lehtonen Juha",
    demo: "Male, 45",
    time: "07:30",
    from: "Nurse K. Lind",
    level: "normal",
    cs: false,
    summary: "Prescription renewal: blood pressure medication. Home readings on target.",
    missing: [],
    findings: [],
  },
  {
    key: "q3",
    name: "Salminen Emma",
    demo: "Female, 33",
    time: "08:05",
    from: "Nurse H. Virtanen",
    level: "normal",
    cs: false,
    summary: "Consultation: itchy rash in elbow creases for two weeks, photo attached.",
    missing: [],
    findings: [],
  },
];

export type PrototypePatient = {
  patient: Patient;
  record: PatientRecord;
  /** Canned result of the prototype (prototype data source only). */
  analysis: Omit<AnalysisResult, "origin">;
};

const NONE: PrototypePatient["analysis"] = { status: "none", summary: "", findings: [], missing: [] };

const h = (id: string, date: string, kind: string, text: string, sortKey: string) => ({ id, ref: id, date, kind, text, sortKey });

export const PROTOTYPE_PATIENTS: PrototypePatient[] = [
  {
    patient: {
      id: "CS-2210",
      name: "Korhonen Mikko",
      demo: "Male, 29",
      time: "08:15",
      visit: "Stomach bug",
      draftNote: "Stomach bug started 2 days ago, diarrhoea and fever 38.2. Same illness in the family.",
    },
    record: {
      history: [h("NOTE-0611", "11.6.2026", "NURSE", "Ankle sprain playing football; ice and rest.", "2026-06-11")],
      labs: [
        { id: "LAB-250203a", ref: "LAB-250203a", date: "3.2.2025", test: "B-Hb", value: "152 g/l", range: "134–167", flag: "", note: "" },
        { id: "LAB-250203b", ref: "LAB-250203b", date: "3.2.2025", test: "P-CRP", value: "< 3 mg/l", range: "< 10", flag: "", note: "" },
      ],
      meds: [],
      refs: [],
    },
    analysis: NONE,
  },
  {
    patient: {
      id: "CS-1042",
      name: "Laine Aino",
      demo: "Female, 64",
      time: "08:45",
      visit: "Fatigue",
      draftNote: "Patient reports increasing fatigue and occasional bloating. No blood in stool noticed.",
    },
    record: {
      history: [
        h("NOTE-0905", "5.9.2026", "PHYSICIAN", "Iron supplement started. Further tests to be considered at follow-up.", "2026-09-05"),
        h("NOTE-0902", "2.9.2026", "NURSE", "Occasional lower abdominal pain; bowel habit changed for about 3 weeks.", "2026-09-02"),
        h("NOTE-0820", "20.8.2026", "NURSE", "Tired all summer. Blood tests taken, follow-up to be booked.", "2026-08-20"),
        h("LAB-0814", "14.8.2026", "LAB", "B-Hb 108 g/l (ref 117–155) · P-Ferritin 9 µg/l (ref 15–150)", "2026-08-14"),
      ],
      labs: [
        { id: "LAB-0814", ref: "LAB-0814", date: "14.8.2026", test: "B-Hb", value: "108 g/l", range: "117–155", flag: "L", note: "" },
        { id: "LAB-0814", ref: "LAB-0814", date: "14.8.2026", test: "P-Ferritin", value: "9 µg/l", range: "15–150", flag: "L", note: "" },
        { id: "LAB-0814b", ref: "LAB-0814b", date: "14.8.2026", test: "E-MCV", value: "76 fl", range: "82–98", flag: "L", note: "" },
        { id: "LAB-0814c", ref: "LAB-0814c", date: "14.8.2026", test: "P-CRP", value: "4 mg/l", range: "< 10", flag: "", note: "" },
        { id: "LAB-250303", ref: "LAB-250303", date: "3.3.2025", test: "B-Hb", value: "131 g/l", range: "117–155", flag: "", note: "Previous value" },
      ],
      meds: [
        { name: "Ferrous sulphate 100 mg", dose: "1 tablet once daily", status: "Started 5 Sep 2026" },
        { name: "Levothyroxine 75 µg", dose: "1 tablet once daily", status: "Long-term" },
      ],
      refs: [],
    },
    analysis: {
      status: "review",
      summary:
        "Today's note alone is non-specific, but earlier records show iron-deficiency anaemia and a change in bowel habit with no follow-up recorded.",
      findings: [
        {
          id: "F1",
          title: "Iron-deficiency anaemia, unresolved",
          detail: "Low Hb and ferritin on 14.8. Iron started 5.9.; no repeat Hb or investigation recorded since.",
          sources: [
            { id: "LAB-0814", label: "LAB-0814" },
            { id: "NOTE-0905", label: "NOTE-0905" },
          ],
          rule: "SUO-03",
          priority: "review",
          ruleSrc: "NICE DG56/HTG690 1.1: offer FIT",
        },
        {
          id: "F2",
          title: "Change in bowel habit",
          detail: "Recorded 2.9. lasting about 3 weeks, with lower abdominal pain. Not mentioned as resolved.",
          sources: [{ id: "NOTE-0902", label: "NOTE-0902" }],
          rule: "SUO-02",
          priority: "review",
          ruleSrc: "NICE DG56/HTG690 1.1: offer FIT",
        },
      ],
      missing: ["No FIT (faecal immunochemical test) result", "No colonoscopy or follow-up Hb after 5.9."],
    },
  },
  {
    patient: {
      id: "CS-4501",
      name: "Nieminen Pertti",
      demo: "Male, 71",
      time: "09:30",
      visit: "Abdominal complaints",
      draftNote: "Blood in stool on several days last week. Weight down about 5 kg in two months, not dieting.",
    },
    record: {
      history: [
        h("LAB-1030", "30.10.2026", "LAB", "F-Hb-FIT 48 µg/g (threshold 10) · Result not acknowledged", "2026-10-30"),
        h("NOTE-1022", "22.10.2026", "NURSE", "Lower abdominal pain for about a month. Stool blood test (FIT) kit given.", "2026-10-22"),
        h("NOTE-0704", "4.7.2026", "NURSE", "Blood pressure check, values on target.", "2026-07-04"),
      ],
      labs: [
        { id: "LAB-1030", ref: "LAB-1030", date: "30.10.2026", test: "F-Hb-FIT", value: "48 µg/g", range: "< 10", flag: "H", note: "Not acknowledged" },
        { id: "LAB-1022", ref: "LAB-1022", date: "22.10.2026", test: "B-Hb", value: "121 g/l", range: "134–167", flag: "L", note: "" },
        { id: "LAB-0704", ref: "LAB-0704", date: "4.7.2026", test: "P-Krea", value: "82 µmol/l", range: "60–100", flag: "", note: "" },
      ],
      meds: [
        { name: "Amlodipine 5 mg", dose: "1 tablet once daily", status: "Long-term" },
        { name: "Atorvastatin 20 mg", dose: "1 tablet in the evening", status: "Long-term" },
      ],
      refs: [
        {
          date: "22.10.2026",
          title: "Test request: F-Hb-FIT",
          detail: "Result arrived 30 Oct 2026. Not yet acknowledged by a physician.",
          status: "Result not acknowledged",
          open: true,
        },
      ],
    },
    analysis: {
      status: "urgent",
      summary: "A positive FIT from 30.10. has not been acted on, and today's note adds rectal bleeding and weight loss.",
      findings: [
        {
          id: "F1",
          title: "Positive FIT not acted on",
          detail: "FIT 48 µg Hb/g on 30.10., above the 10 µg/g threshold. No physician review or referral recorded since.",
          sources: [{ id: "LAB-1030", label: "LAB-1030" }],
          rule: "SUO-08",
          priority: "urgent",
          ruleSrc: "NICE DG56/HTG690 1.2: suspected cancer pathway referral",
        },
        {
          id: "F2",
          title: "Rectal bleeding and weight loss, age 50+",
          detail: "Reported today, after abdominal pain recorded on 22.10.",
          sources: [
            { id: "Today", label: "Today" },
            { id: "NOTE-1022", label: "NOTE-1022" },
          ],
          rule: "SUO-06",
          priority: "review",
          ruleSrc: "NICE DG56/HTG690 1.1: offer FIT",
        },
      ],
      missing: ["No physician review of the FIT result", "No referral recorded"],
    },
  },
  {
    patient: {
      id: "CS-3387",
      name: "Heikkinen Sari",
      demo: "Female, 58",
      time: "10:00",
      visit: "Fatigue",
      draftNote: "Tired for the past few weeks, no other symptoms. No abdominal complaints.",
    },
    record: {
      history: [
        h("LAB-0702", "2.7.2026", "LAB", "B-Hb 128 g/l (ref 117–155)", "2026-07-02"),
        h("NOTE-0618", "18.6.2026", "PHYSICIAN", "Colonoscopy and gastroscopy: normal. Cause of anaemia investigated.", "2026-06-18"),
        h("LAB-0512", "12.5.2026", "LAB", "B-Hb 112 g/l (ref 117–155) · P-Ferritin 11 µg/l", "2026-05-12"),
      ],
      labs: [
        { id: "LAB-0702", ref: "LAB-0702", date: "2.7.2026", test: "B-Hb", value: "128 g/l", range: "117–155", flag: "", note: "" },
        { id: "LAB-0512", ref: "LAB-0512", date: "12.5.2026", test: "B-Hb", value: "112 g/l", range: "117–155", flag: "L", note: "" },
        { id: "LAB-0512", ref: "LAB-0512", date: "12.5.2026", test: "P-Ferritin", value: "11 µg/l", range: "15–150", flag: "L", note: "" },
      ],
      meds: [{ name: "Ferrous sulphate 100 mg", dose: "1 tablet once daily", status: "Ended 30 Jun 2026" }],
      refs: [
        {
          date: "14.5.2026",
          title: "Referral: gastroenterology",
          detail: "Colonoscopy and gastroscopy done 18 Jun 2026, normal findings.",
          status: "Closed",
          open: false,
        },
      ],
    },
    analysis: NONE,
  },
];
