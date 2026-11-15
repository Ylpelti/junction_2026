/** Display-only formatting. No rounding, thresholds or unit conversions. */
export function formatDecimal(value: string): string {
  if (!/^-?\d+(\.\d+)?$/.test(value)) return value;
  return (value.includes(".") ? value.replace(/\.?0+$/, "") : value);
}
export function formatUnit(unit: string | null): string {
  const labels: Record<string, string> = { "ug/g": "µg/g", "ug/L": "µg/L", "ug/l": "µg/L", "g/l": "g/L" };
  return unit ? labels[unit] ?? unit : "";
}
export function formatMeasurement(value: string | null, unit: string | null): string {
  return value === null ? "" : [formatDecimal(value), formatUnit(unit)].filter(Boolean).join(" ");
}
