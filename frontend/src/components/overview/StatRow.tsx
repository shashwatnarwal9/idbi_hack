import type { LucideIcon } from "lucide-react";

import { StatCard } from "../StatCard";

export interface OverviewStat {
  label: string;
  value: string;
  sub: string;
  trend?: string;
  trendKind: "positive" | "negative" | "neutral";
  icon: LucideIcon;
}

interface StatRowProps {
  stats: OverviewStat[];
}

export function StatRow({ stats }: StatRowProps) {
  return (
    <div className="grid gap-5 md:grid-cols-3">
      {stats.map((s) => (
        <StatCard
          key={s.label}
          label={s.label}
          value={s.value}
          delta={s.trend}
          deltaKind={s.trendKind}
          hint={s.sub}
          icon={s.icon}
        />
      ))}
    </div>
  );
}
