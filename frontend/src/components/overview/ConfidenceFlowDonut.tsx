import { Cell, Pie, PieChart, ResponsiveContainer } from "recharts";

import { COLORS } from "../../lib/colors";
import type { ConfidenceBand, ConfidenceSlice } from "../../mocks/types";
import { Card } from "../Card";

const BAND_COLOR: Record<ConfidenceBand, string> = {
  high: COLORS.emerald,
  medium: COLORS.amber,
  low: COLORS.negative,
};

const BAND_LABEL: Record<ConfidenceBand, string> = {
  high: "High confidence",
  medium: "Medium confidence",
  low: "Low confidence",
};

interface ConfidenceFlowDonutProps {
  split: ConfidenceSlice[];
}

/** High/Medium/Low trust split with the high-trust share in the center. */
export function ConfidenceFlowDonut({ split }: ConfidenceFlowDonutProps) {
  const total = split.reduce((sum, s) => sum + s.count, 0);
  const high = split.find((s) => s.band === "high")?.count ?? 0;
  const highPct = total > 0 ? Math.round((high / total) * 100) : 0;

  return (
    <Card
      title="Confidence Flow"
      subtitle="How much each income estimate can be trusted"
    >
      <div className="relative mx-auto h-48 w-48">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={split}
              dataKey="count"
              nameKey="band"
              innerRadius={62}
              outerRadius={86}
              paddingAngle={2}
              stroke="#ffffff"
              strokeWidth={2}
            >
              {split.map((slice) => (
                <Cell key={slice.band} fill={BAND_COLOR[slice.band]} />
              ))}
            </Pie>
          </PieChart>
        </ResponsiveContainer>
        <div className="pointer-events-none absolute inset-0 flex flex-col items-center justify-center">
          <div className="text-2xl font-semibold">{highPct}%</div>
          <div className="text-xs text-ink-muted">high trust</div>
        </div>
      </div>

      <ul className="mt-4 space-y-2">
        {split.map((slice) => (
          <li key={slice.band} className="flex items-center gap-2 text-sm">
            <span
              className="size-2.5 rounded-full"
              style={{ backgroundColor: BAND_COLOR[slice.band] }}
            />
            <span className="text-ink-soft">{BAND_LABEL[slice.band]}</span>
            <span className="ml-auto font-medium">
              {slice.count}
              <span className="ml-1 text-xs font-normal text-ink-muted">
                ({total > 0 ? Math.round((slice.count / total) * 100) : 0}%)
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}
