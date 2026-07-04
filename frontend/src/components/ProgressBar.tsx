export type ProgressTone = "brand" | "positive" | "warning" | "danger";

const TONE_FILL: Record<ProgressTone, string> = {
  brand: "bg-forest",
  positive: "bg-emerald",
  warning: "bg-amber",
  danger: "bg-negative",
};

interface ProgressBarProps {
  /** Fraction in [0, 1]. */
  value: number;
  tone?: ProgressTone;
}

export function ProgressBar({ value, tone = "brand" }: ProgressBarProps) {
  const pct = Math.min(Math.max(value, 0), 1) * 100;
  return (
    <div
      className="h-2 w-full overflow-hidden rounded-full bg-sage"
      role="progressbar"
      aria-valuenow={Math.round(pct)}
      aria-valuemin={0}
      aria-valuemax={100}
    >
      <div
        className={`h-full rounded-full ${TONE_FILL[tone]} transition-[width]`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}
