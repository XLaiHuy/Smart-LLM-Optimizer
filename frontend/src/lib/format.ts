export function formatMetric(
  value: number | null | undefined,
  locale: string,
  unit = "",
): string | null {
  return value == null
    ? null
    : `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(value)}${unit}`;
}

export function knownTokenTotal(
  input: number | null | undefined,
  output: number | null | undefined,
): number | null {
  return input == null || output == null ? null : input + output;
}

export function formatCost(
  value: string | null | undefined,
  locale: string,
): string | null {
  if (value == null) return null;
  return new Intl.NumberFormat(locale, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 9,
  }).format(Number(value));
}
