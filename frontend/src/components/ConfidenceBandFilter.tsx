import type { ConfidenceBand } from "../mocks/types";

type BandFilter = "all" | ConfidenceBand;

interface Segment {
  value: BandFilter;
  label: string;
  /** active (selected) pill classes, color-matched to the confidence badges */
  active: string;
  /** small colour dot so the band colour is visible even when unselected */
  dot: string;
}

// Colours mirror the Badge tones: high=green, medium=amber, low=red.
const SEGMENTS: Segment[] = [
  { value: "all", label: "All", active: "bg-forest text-white", dot: "" },
  {
    value: "high",
    label: "High",
    active: "bg-mint text-forest-deep",
    dot: "bg-forest",
  },
  {
    value: "medium",
    label: "Medium",
    active: "bg-amber text-white",
    dot: "bg-amber",
  },
  {
    value: "low",
    label: "Low",
    active: "bg-negative text-white",
    dot: "bg-negative",
  },
];

interface Props {
  value: BandFilter;
  counts: Partial<Record<BandFilter, number>>;
  onChange: (value: BandFilter) => void;
}

/**
 * Segmented single-select for confidence band: [All][High][Medium][Low], each
 * showing its real count. Rendered as an ARIA radiogroup so it is fully
 * keyboard-operable (Tab in, arrow keys move + select). Presentation only —
 * the parent maps the value onto the /customers/ranked?confidence= query.
 */
export function ConfidenceBandFilter({ value, counts, onChange }: Props) {
  const move = (dir: 1 | -1) => {
    const i = SEGMENTS.findIndex((s) => s.value === value);
    const next = (i + dir + SEGMENTS.length) % SEGMENTS.length;
    onChange(SEGMENTS[next].value);
  };

  return (
    <div
      role="radiogroup"
      aria-label="Filter by confidence band"
      className="inline-flex flex-wrap items-center gap-1 rounded-xl border border-line bg-sage/40 p-1"
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowDown") {
          e.preventDefault();
          move(1);
        } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
          e.preventDefault();
          move(-1);
        }
      }}
    >
      {SEGMENTS.map((seg) => {
        const selected = seg.value === value;
        const count = counts[seg.value];
        return (
          <button
            key={seg.value}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            onClick={() => onChange(seg.value)}
            className={`inline-flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-colors ${
              selected
                ? seg.active
                : "text-ink-soft hover:bg-white/70"
            }`}
          >
            {seg.dot && (
              <span className={`h-2 w-2 rounded-full ${seg.dot}`} aria-hidden />
            )}
            {seg.label}
            {count !== undefined && (
              <span className={selected ? "opacity-80" : "text-ink-muted"}>
                ({count})
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
