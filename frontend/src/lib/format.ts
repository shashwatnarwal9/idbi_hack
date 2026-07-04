/** Indian-locale rupee formatting: 67934 -> "₹67,934". */
export function inr(value: number): string {
  return `₹${Math.round(value).toLocaleString("en-IN")}`;
}

/** Compact rupee axis labels: 60000 -> "₹60k". */
export function inrCompact(value: number): string {
  return value >= 1000 ? `₹${Math.round(value / 1000)}k` : `₹${value}`;
}
