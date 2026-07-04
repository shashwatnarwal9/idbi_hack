import { CheckCircle2, Download, XCircle } from "lucide-react";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { DataTable, type Column } from "../components/DataTable";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import { StatCard } from "../components/StatCard";
import { downloadCsv } from "../lib/download";
import { inr } from "../lib/format";
import type { LoanAssessmentRow, LoanAssessmentSummary } from "../lib/apiTypes";
import { useApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

type StatusFilter = "all" | "eligible" | "not_eligible";

function exportEligible(product: string, rows: LoanAssessmentRow[]) {
  const header = "customer_id,name,suggested_amount,prospect_score\n";
  const body = rows
    .filter((r) => r.status === "eligible")
    .map(
      (r) =>
        `${r.customer_id},"${r.name}",${r.suggested_amount ?? ""},${(r.score * 100).toFixed(1)}`,
    )
    .join("\n");
  downloadCsv(`${product}-eligible.csv`, header + body);
}

export function LoanAssessment() {
  const navigate = useNavigate();
  const summary = useApi<LoanAssessmentSummary>("/loan-assessment/summary");
  const [product, setProduct] = useState("personal");
  const [status, setStatus] = useState<StatusFilter>("all");

  const path = useMemo(
    () => `/loan-assessment/${product}?status=${status}`,
    [product, status],
  );
  const rows = useApi<LoanAssessmentRow[]>(path);

  const products = summary.data?.products ?? [];
  const deepest = products.reduce(
    (best, p) => (p.eligible > (best?.eligible ?? -1) ? p : best),
    products[0],
  );
  const active = products.find((p) => p.product === product);
  const total = summary.data?.customers ?? 0;

  const columns: Column<LoanAssessmentRow>[] = [
    {
      header: "Customer",
      cell: (r) => (
        <div className="leading-tight">
          <div className="flex items-center gap-1.5 font-medium">
            {r.reviewed && <CheckCircle2 size={13} className="shrink-0 text-emerald" />}
            {r.name}
          </div>
          <div className="flex items-center gap-1.5 font-mono text-xs text-ink-muted">
            {r.customer_id}
            {r.source === "uploaded" && (
              <span className="rounded bg-sage px-1 text-[10px] not-italic text-ink-soft">
                uploaded
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      header: "Eligibility",
      cell: (r) =>
        r.status === "eligible" ? (
          <span className="inline-flex items-center gap-1 text-sm font-medium text-emerald">
            <CheckCircle2 size={14} />
            Eligible
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-sm text-ink-muted">
            <XCircle size={14} />
            {r.reason}
          </span>
        ),
    },
    {
      header: "Suggested",
      align: "right",
      cell: (r) =>
        r.suggested_amount !== null ? (
          <span className="font-semibold">{inr(r.suggested_amount)}</span>
        ) : (
          <span className="text-ink-muted">—</span>
        ),
    },
    {
      header: "Score /100",
      align: "right",
      cell: (r) => <span className="font-semibold">{(r.score * 100).toFixed(1)}</span>,
    },
    {
      header: "Confidence",
      cell: (r) => <Badge tone={BAND_TONE[r.confidence_band]}>{r.confidence_band}</Badge>,
    },
  ];

  return (
    <div className="space-y-5">
      <SectionHeader description="Per-product eligibility across the book, from the loan-product rules" />

      {summary.loading && <Loading />}
      {summary.error && <ErrorNote message={summary.error} />}
      {summary.data && (
        <div className="grid gap-5 md:grid-cols-4">
          {products.map((p) => (
            <StatCard
              key={p.product}
              label={p.label}
              value={`${p.eligible} / ${total}`}
              hint={
                p.product === deepest?.product
                  ? "deepest eligible pool"
                  : `${Math.round((p.eligible / total) * 100)}% eligible`
              }
            />
          ))}
        </div>
      )}

      <Card>
        <div className="mb-4 flex flex-wrap items-center gap-2">
          <div className="flex rounded-xl bg-sage p-1">
            {products.map((p) => (
              <button
                key={p.product}
                type="button"
                onClick={() => setProduct(p.product)}
                className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
                  product === p.product
                    ? "bg-white text-forest-deep shadow-sm"
                    : "text-ink-soft hover:text-ink"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="ml-auto flex items-center gap-2">
            {(["all", "eligible", "not_eligible"] as StatusFilter[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setStatus(s)}
                className={`rounded-full px-3 py-1 text-xs font-medium ${
                  status === s
                    ? "bg-forest text-white"
                    : "bg-sage text-ink-soft hover:bg-mint"
                }`}
              >
                {s === "not_eligible" ? "not eligible" : s}
              </button>
            ))}
            <button
              type="button"
              onClick={() => rows.data && exportEligible(product, rows.data)}
              className="inline-flex items-center gap-2 rounded-xl border border-line px-3 py-1.5 text-xs font-medium text-ink-soft hover:bg-sage"
            >
              <Download size={14} />
              Export list
            </button>
          </div>
        </div>

        {active && (
          <p className="mb-3 text-xs text-ink-muted">
            {active.label}: <span className="font-semibold text-emerald">{active.eligible} eligible</span>{" "}
            · {active.not_eligible} not eligible ·{" "}
            {Math.round((active.eligible / total) * 100)}% of {total} customers.
            Amounts are illustrative, not offers.
          </p>
        )}

        {rows.loading ? (
          <Loading />
        ) : rows.error ? (
          <ErrorNote message={rows.error} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows.data ?? []}
            rowKey={(r) => r.customer_id}
            onRowClick={(r) => navigate(`/customers?id=${r.customer_id}`)}
          />
        )}
      </Card>
    </div>
  );
}
