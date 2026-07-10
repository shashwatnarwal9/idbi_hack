import { useLocation, useNavigate, useParams } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { BackButton, type NavOrigin } from "../components/BackButton";
import { Card } from "../components/Card";
import { DataTable, type Column } from "../components/DataTable";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import type { ConfidenceBand } from "../mocks/types";
import type { QuadrantCustomer } from "../lib/apiTypes";
import { useApi } from "../lib/useApi";

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

const QUADRANT_LABEL: Record<string, string> = {
  act_now: "Act now",
  nurture: "Nurture",
  downsell: "Downsell",
  exclude: "Exclude",
};

/** Customers in one capacity×intent quadrant. Rows open the customer's Intent
 * page carrying the SAME origin forward, so its Back returns to where this list
 * was opened from (per the shared nav pattern). */
export function QuadrantList() {
  const { quadrant = "" } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const origin = (location.state ?? null) as NavOrigin | null;
  const back: NavOrigin = origin ?? { from: "/", fromLabel: "Overview" };

  const { data, loading, error } = useApi<QuadrantCustomer[]>(
    `/intent/quadrant/${encodeURIComponent(quadrant)}`,
  );

  const columns: Column<QuadrantCustomer>[] = [
    { header: "#", align: "right", cell: (r) => <span>{r.intent_decile}</span> },
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
      header: "Intent",
      align: "right",
      cell: (r) => <span className="font-semibold">{r.intent.toFixed(0)}</span>,
    },
    {
      header: "Best fit",
      cell: (r) => (
        <span className="capitalize text-ink-soft">{r.best_fit_product ?? "—"}</span>
      ),
    },
    {
      header: "Score /100",
      align: "right",
      cell: (r) => (
        <span>{r.prospect_score !== null ? (r.prospect_score * 100).toFixed(1) : "—"}</span>
      ),
    },
    {
      header: "Confidence",
      cell: (r) => <Badge tone={BAND_TONE[r.confidence_band]}>{r.confidence_band}</Badge>,
    },
  ];

  return (
    <div className="space-y-5">
      <BackButton fallback={back.from} fallbackLabel={back.fromLabel} />
      <SectionHeader
        description={`${QUADRANT_LABEL[quadrant] ?? quadrant} customers, click a row to open their intent`}
      />
      <Card>
        {loading ? (
          <Loading />
        ) : error ? (
          <ErrorNote message={error} />
        ) : (
          <DataTable
            columns={columns}
            rows={data ?? []}
            rowKey={(r) => r.customer_id}
            onRowClick={(r) =>
              navigate(`/intent/${encodeURIComponent(r.customer_id)}`, { state: back })
            }
          />
        )}
      </Card>
    </div>
  );
}
