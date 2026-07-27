export function asNumber(value: unknown): number {
  if (typeof value === "number") return value;
  if (typeof value === "string") return Number(value) || 0;
  return 0;
}

export function money(value: unknown): string {
  return new Intl.NumberFormat("zh-CN", {
    style: "currency",
    currency: "CNY",
    maximumFractionDigits: 0,
    notation: Math.abs(asNumber(value)) >= 1_000_000 ? "compact" : "standard",
  }).format(asNumber(value));
}

export function integer(value: unknown): string {
  return new Intl.NumberFormat("zh-CN", {
    maximumFractionDigits: 0,
  }).format(asNumber(value));
}

export function percent(value: unknown): string {
  if (value === null || value === undefined) return "—";
  return new Intl.NumberFormat("zh-CN", {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(asNumber(value));
}

export function compactId(value: unknown): string {
  const text = String(value ?? "—");
  if (text.length <= 18) return text;
  return `${text.slice(0, 10)}…${text.slice(-5)}`;
}

