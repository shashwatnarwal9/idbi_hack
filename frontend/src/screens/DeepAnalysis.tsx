import { CheckCircle2, MoveDownRight, MoveUpRight } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { ConfidenceBandFilter } from "../components/ConfidenceBandFilter";
import { DataTable, type Column } from "../components/DataTable";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import type { OverviewSummary, RankedCustomer } from "../lib/apiTypes";
import { useApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

/** "all" plus the three bands — the segmented selector value. */
type BandFilter = "all" | ConfidenceBand;

function rankedPath(filter: BandFilter, order: "asc" | "desc"): string {
  const params = new URLSearchParams({ order });
  if (filter !== "all") params.append("confidence", filter);
  return `/customers/ranked?${params.toString()}`;
}

export function DeepAnalysis() {
  const navigate = useNavigate();
  const [filter, setFilter] = useState<BandFilter>("all");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const path = useMemo(() => rankedPath(filter, order), [filter, order]);
  const { data, error, loading } = useApi<RankedCustomer[]>(path);
  // Real per-band counts from the serving store (shared cache with Overview).
  const summary = useApi<OverviewSummary>("/overview/summary");
  const bands = summary.data?.bands;
  const counts = {
    all: bands ? bands.high + bands.medium + bands.low : undefined,
    high: bands?.high,
    medium: bands?.medium,
    low: bands?.low,
  };

  const columns: Column<RankedCustomer>[] = [
    { header: "#", align: "right", cell: (r) => <span>{r.rank}</span> },
    {
      header: "Customer",
      cell: (r) => (
        <div className="leading-tight">
          <div className="font-medium">{r.name}</div>
          <div className="font-mono text-xs text-ink-muted">{r.customer_id}</div>
        </div>
      ),
    },
    {
      header: "Score /100",
      align: "right",
      cell: (r) => (
        <span className="font-semibold">{(r.score * 100).toFixed(1)}</span>
      ),
    },
    {
      header: "Confidence",
      cell: (r) => <Badge tone={BAND_TONE[r.band]}>{r.band}</Badge>,
    },
    {
      header: "Top signals",
      cell: (r) => (
        <div className="flex flex-wrap gap-1.5">
          {r.reasons.slice(0, 3).map((reason) => (
            <span
              key={reason.feature}
              className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 font-mono text-[11px] ${
                reason.shap > 0
                  ? "bg-mint text-forest-deep"
                  : "bg-negative/10 text-negative"
              }`}
            >
              {reason.shap > 0 ? (
                <MoveUpRight size={10} />
              ) : (
                <MoveDownRight size={10} />
              )}
              {reason.feature}
            </span>
          ))}
        </div>
      ),
    },
    {
      header: "Reviewed",
      cell: (r) =>
        r.reviewed ? (
          <CheckCircle2 size={16} className="text-emerald" />
        ) : (
          <span className="text-ink-muted">—</span>
        ),
    },
  ];

  return (
    <div className="space-y-5">
      <SectionHeader description="Every customer, ranked live by prospect score from the serving store" />

      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-3">
          <ConfidenceBandFilter value={filter} counts={counts} onChange={setFilter} />
          <button
            type="button"
            onClick={() => setOrder((o) => (o === "desc" ? "asc" : "desc"))}
            className="ml-auto rounded-xl border border-line px-3 py-1.5 text-xs font-medium text-ink-soft hover:bg-sage"
          >
            {order === "desc" ? "Best first" : "Worst first"}
          </button>
        </div>

        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorNote message={error} />
        ) : (
          <>
            <p className="mb-2 text-xs text-ink-muted">
              {data?.length ?? 0} customers · click a row to open the profile
            </p>
            <DataTable
              columns={columns}
              rows={data ?? []}
              rowKey={(r) => r.customer_id}
              onRowClick={(r) => navigate(`/customers?id=${r.customer_id}`)}
            />
          </>
        )}
      </Card>
    </div>
  );
}
