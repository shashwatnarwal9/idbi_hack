import { TrendingDown, TrendingUp, type LucideIcon } from "lucide-react";

interface StatCardProps {
  label: string;
  value: string;
  /** Optional change annotation, e.g. "+₹15,400 vs declared". */
  delta?: string;
  deltaKind?: "positive" | "negative" | "neutral";
  icon?: LucideIcon;
  hint?: string;
}

export function StatCard({
  label,
  value,
  delta,
  deltaKind = "neutral",
  icon: Icon,
  hint,
}: StatCardProps) {
  const deltaColor =
    deltaKind === "positive"
      ? "text-emerald"
      : deltaKind === "negative"
        ? "text-negative"
        : "text-ink-muted";
  const DeltaIcon = deltaKind === "negative" ? TrendingDown : TrendingUp;

  return (
    <div className="rounded-2xl border border-line bg-white p-5 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div className="text-xs font-medium uppercase tracking-wide text-ink-muted">
          {label}
        </div>
        {Icon && (
          <div className="rounded-xl bg-mint p-2 text-forest">
            <Icon size={16} strokeWidth={1.8} />
          </div>
        )}
      </div>
      <div className="mt-2 text-2xl font-semibold tracking-tight">{value}</div>
      {delta && (
        <div className={`mt-1.5 flex items-center gap-1 text-xs font-medium ${deltaColor}`}>
          {deltaKind !== "neutral" && <DeltaIcon size={13} />}
          {delta}
        </div>
      )}
      {hint && <div className="mt-1 text-xs text-ink-muted">{hint}</div>}
    </div>
  );
}
