import type { ClinicalExplanation } from "../lib/types";

export function ClinicalExplanationCard({ value, triggeredRuleIds = [], showSummary = true }: {
  value: ClinicalExplanation; triggeredRuleIds?: string[]; showSummary?: boolean;
}) {
  // Join by the backend's trigger_rule_id, not text, array order or review flag.
  const matchedRules = value.rule_results.filter(item => item.rule_reference && triggeredRuleIds.includes(item.rule_reference.trigger_rule_id));
  const statements = [...value.findings, ...value.mathematical_outputs, ...matchedRules];
  return (
    <details className="rounded-xl border border-line bg-white p-3 text-sm" lang="en">
      <summary className="cursor-pointer font-semibold">{showSummary ? "Clinical summary" : "Clinical summary evidence"} · {value.mode === "llm" ? "LLM-assisted" : value.mode === "fallback" ? "deterministic" : "unavailable"}</summary>
      {showSummary && <p>{value.summary_en}</p>}
      {statements.map(item => <p key={item.key} className="mt-2">{item.text_en}</p>)}
      <details className="mt-3 text-mute">
        <summary className="cursor-pointer">Source details, uncertainty and validation limitations</summary>
        {statements.filter(item => item.observation_ids.length).map(item => <p key={item.key} className="break-all text-xs">{item.key} · Source ID: {item.observation_ids.join(", ")}</p>)}
        {value.limitations.map((item, index) => <p key={`${item.code}-${index}`} className="mt-2">{item.text_en}</p>)}
        {value.issues?.map((issue, index) => <p key={`${issue.code}-${index}`} className="mt-2">{issue.code}: {issue.message}</p>)}
        {value.provenance && <p>{value.provenance.name} · {value.provenance.method} · {value.provenance.version}</p>}
      </details>
    </details>
  );
}
