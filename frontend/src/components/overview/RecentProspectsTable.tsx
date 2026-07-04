import { CheckCircle2, MoveDownRight, MoveUpRight } from "lucide-react";

import type { ConfidenceBand, ReasonChip, RecentProspect } from "../../mocks/types";
import { Badge, type BadgeTone } from "../Badge";
import { Card } from "../Card";
import { DataTable, type Column } from "../DataTable";

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

const BAND_LABEL: Record<ConfidenceBand, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

function ReasonChipPill({ chip }: { chip: ReasonChip }) {
  const up = chip.direction === "up";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] ${
        up ? "bg-mint text-forest-deep" : "bg-negative/10 text-negative"
      }`}
    >
      {up ? <MoveUpRight size={10} /> : <MoveDownRight size={10} />}
      {chip.feature}
    </span>
  );
}

const COLUMNS: Column<RecentProspect>[] = [
  {
    header: "Customer",
    cell: (row) => (
      <div className="flex items-center gap-3">
        <div className="flex size-9 shrink-0 items-center justify-center rounded-full bg-mint text-xs font-semibold text-forest-deep">
          {initials(row.name)}
        </div>
        <div className="leading-tight">
          <div className="flex items-center gap-1.5 font-medium">
            {row.reviewed && (
              <CheckCircle2 size={14} className="shrink-0 text-emerald" />
            )}
            {row.name}
          </div>
          <div className="font-mono text-xs text-ink-muted">{row.customerId}</div>
        </div>
      </div>
    ),
  },
  {
    header: "Score",
    align: "right",
    cell: (row) => (
      <span className="font-semibold">
        {row.score}
        <span className="font-normal text-ink-muted"> /100</span>
      </span>
    ),
  },
  {
    header: "Confidence",
    cell: (row) => <Badge tone={BAND_TONE[row.band]}>{BAND_LABEL[row.band]}</Badge>,
  },
  {
    header: "Top signals",
    cell: (row) => (
      <div className="flex flex-wrap gap-1.5">
        {row.reasons.map((chip) => (
          <ReasonChipPill key={chip.feature} chip={chip} />
        ))}
      </div>
    ),
  },
];

interface RecentProspectsTableProps {
  prospects: RecentProspect[];
  onSelect?: (prospect: RecentProspect) => void;
}

export function RecentProspectsTable({
  prospects,
  onSelect,
}: RecentProspectsTableProps) {
  return (
    <Card
      title="Top Prospects"
      subtitle="Best-scored customers right now; a check marks analyst-reviewed"
    >
      <DataTable
        columns={COLUMNS}
        rows={prospects}
        rowKey={(row) => row.customerId}
        onRowClick={onSelect}
      />
    </Card>
  );
}
