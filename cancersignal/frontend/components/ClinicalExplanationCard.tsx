import type { ClinicalExplanation } from "../lib/types";

export function ClinicalExplanationCard({ value }: { value: ClinicalExplanation }) {
  return (
    <details className="rounded-xl border border-line bg-white p-3 text-sm" lang="fi">
      <summary className="cursor-pointer font-semibold">Kliininen yhteenveto · {value.mode === "llm" ? "LLM-avusteinen" : value.mode === "fallback" ? "deterministinen" : "ei saatavilla"}</summary>
      <p>{value.summary_fi}</p>
      {[...value.findings, ...value.mathematical_outputs, ...value.rule_results].map((item) => (
        <p key={item.key} className="mt-2">
          {item.text_fi}
          {item.observation_ids.length > 0 && <small className="block break-all text-mute">Lähde-ID: {item.observation_ids.join(", ")}</small>}
        </p>
      ))}
      {value.limitations.map((item, index) => <p key={`${item.code}-${index}`} className="mt-2 text-mute">{item.text_fi}</p>)}
    </details>
  );
}
