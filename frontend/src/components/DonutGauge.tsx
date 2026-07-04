interface DonutGaugeProps {
  /** Fraction in [0, 1]. */
  value: number;
  /** Caption under the gauge. */
  label?: string;
  /** Center text override; defaults to the value as a percentage. */
  valueLabel?: string;
  size?: number;
}

/** Single-value donut: green arc on a sage track with the value centered. */
export function DonutGauge({ value, label, valueLabel, size = 120 }: DonutGaugeProps) {
  const clamped = Math.min(Math.max(value, 0), 1);
  const stroke = 10;
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;

  return (
    <div className="inline-flex flex-col items-center gap-1.5">
      <svg width={size} height={size} role="img" aria-label={label ?? "gauge"}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          className="stroke-sage"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={`${clamped * c} ${c}`}
          transform={`rotate(-90 ${size / 2} ${size / 2})`}
          className="stroke-emerald"
        />
        <text
          x="50%"
          y="50%"
          dominantBaseline="central"
          textAnchor="middle"
          className="fill-ink text-xl font-semibold"
        >
          {valueLabel ?? `${Math.round(clamped * 100)}%`}
        </text>
      </svg>
      {label && <span className="text-xs text-ink-muted">{label}</span>}
    </div>
  );
}
