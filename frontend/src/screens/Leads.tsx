import { Download, Flame } from "lucide-react";
import { useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { DataTable, type Column } from "../components/DataTable";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import { apiPost } from "../lib/api";
import type { LeadRow, LeadsSummary } from "../lib/apiTypes";
import { downloadCsv } from "../lib/download";
import { inr } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

const PRODUCTS = [
  { key: "personal", label: "Personal" },
  { key: "auto", label: "Auto" },
  { key: "home", label: "Home" },
  { key: "mortgage", label: "Mortgage" },
] as const;

const BAND_TONE: Record<ConfidenceBand, BadgeTone> = {
  high: "success",
  medium: "warning",
  low: "danger",
};

const QUADRANT_TONE: Record<string, BadgeTone> = {
  act_now: "success",
  nurture: "brand",
  downsell: "warning",
  exclude: "neutral",
};

const QUADRANT_LABEL: Record<string, string> = {
  act_now: "Act now",
  nurture: "Nurture",
  downsell: "Downsell",
  exclude: "Exclude",
};

type BandFilter = "" | ConfidenceBand;
type QuadrantFilter = "" | "act_now" | "nurture" | "downsell" | "exclude";

function exportLeads(product: string, rows: LeadRow[]) {
  const header =
    "rank,customer_id,name,quadrant,intent,prospect_score,best_repayable,urgency,confidence,source,contacted\n";
  const body = rows
    .map((r) =>
      [
        r.rank,
        r.customer_id,
        `"${r.name}"`,
        r.quadrant,
        r.product_intent.toFixed(1),
        r.prospect_score !== null ? (r.prospect_score * 100).toFixed(1) : "",
        Math.round(r.best_repayable_amount),
        r.urgency ? "urgent" : "",
        r.confidence_band,
        r.source,
        r.contacted ? "contacted" : "",
      ].join(","),
    )
    .join("\n");
  downloadCsv(`${product}-leads.csv`, header + body);
}

export function Leads() {
  const navigate = useNavigate();
  // Filters live in the URL so a view (e.g. the Act-now list) is restorable,
  // the shared Back button returns to the exact leads URL it came from.
  const [searchParams, setSearchParams] = useSearchParams();
  const product = searchParams.get("product") ?? "personal";
  const quadrant = (searchParams.get("quadrant") ?? "") as QuadrantFilter;
  const band = (searchParams.get("band") ?? "") as BandFilter;
  const source = searchParams.get("source") ?? "";
  const minDecile = Number(searchParams.get("min_decile") ?? 0);
  const [contacted, setContacted] = useState<Record<string, boolean>>({});

  const setParam = (key: string, value: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("product", product); // keep the tab pinned in the URL
    if (value) next.set(key, value);
    else next.delete(key);
    setSearchParams(next);
  };

  const summary = useApi<LeadsSummary>("/leads/summary");
  const apiParams = new URLSearchParams({ min_decile: String(minDecile) });
  if (quadrant) apiParams.set("quadrant", quadrant);
  if (band) apiParams.set("band", band);
  if (source) apiParams.set("source", source);
  const rows = useApi<LeadRow[]>(`/leads/${product}?${apiParams.toString()}`);

  // The exact current view, used as the Back origin when opening a customer.
  const currentParams = new URLSearchParams(searchParams);
  currentParams.set("product", product);
  const backOrigin = {
    from: `/leads?${currentParams.toString()}`,
    fromLabel: quadrant === "act_now" ? "Act-now leads" : "Leads",
  };
  const openCustomer = (r: LeadRow) =>
    navigate(`/intent/${encodeURIComponent(r.customer_id)}`, { state: backOrigin });

  const summaryRow = summary.data?.products.find((p) => p.product === product);
  const shownRepayable = (rows.data ?? [])
    .filter((r) => r.eligible)
    .reduce((sum, r) => sum + r.best_repayable_amount, 0);

  const isContacted = (r: LeadRow) =>
    contacted[`${product}:${r.customer_id}`] ?? r.contacted;

  const toggleContacted = async (r: LeadRow) => {
    const key = `${product}:${r.customer_id}`;
    const next = !isContacted(r);
    setContacted((c) => ({ ...c, [key]: next })); // optimistic; changes no score
    await apiPost(`/leads/${product}/${r.customer_id}/contacted`, {
      contacted: next,
      contacted_by: "analyst",
    });
  };

  const columns: Column<LeadRow>[] = [
    { header: "#", align: "right", cell: (r) => <span>{r.rank}</span> },
    {
      header: "Customer",
      cell: (r) => (
        <div className="leading-tight">
          <div className="flex items-center gap-1.5 font-medium">
            {r.urgency && <Flame size={13} className="shrink-0 text-negative" />}
            {r.name}
          </div>
          <div className="flex items-center gap-1.5 font-mono text-xs text-ink-muted">
            {r.customer_id}
            {r.source === "uploaded" && (
              <span className="rounded bg-sage px-1 text-[10px] text-ink-soft">
                uploaded
              </span>
            )}
          </div>
        </div>
      ),
    },
    {
      header: "Quadrant",
      cell: (r) => (
        <Badge tone={QUADRANT_TONE[r.quadrant] ?? "neutral"}>
          {QUADRANT_LABEL[r.quadrant] ?? r.quadrant}
        </Badge>
      ),
    },
    {
      header: "Intent",
      align: "right",
      cell: (r) => <span className="font-semibold">{r.product_intent.toFixed(0)}</span>,
    },
    {
      header: "Score /100",
      align: "right",
      cell: (r) => (
        <span>{r.prospect_score !== null ? (r.prospect_score * 100).toFixed(1) : "—"}</span>
      ),
    },
    {
      header: "Best repayable",
      align: "right",
      cell: (r) => <span className="font-semibold">{inr(r.best_repayable_amount)}</span>,
    },
    {
      header: "Trigger",
      cell: (r) => <span className="text-xs text-ink-soft">{r.trigger}</span>,
    },
    {
      header: "Confidence",
      cell: (r) => <Badge tone={BAND_TONE[r.confidence_band]}>{r.confidence_band}</Badge>,
    },
    {
      header: "Contacted",
      align: "right",
      cell: (r) => (
        <input
          type="checkbox"
          checked={isContacted(r)}
          onChange={() => void toggleContacted(r)}
          onClick={(e) => e.stopPropagation()}
          className="size-4 accent-forest"
          title="Workflow only, does not change any score"
        />
      ),
    },
  ];

  return (
    <div className="space-y-5">
      <SectionHeader description="Ranked leads per product by lead score, eligibility × intent × capacity × urgency" />

      <div className="flex flex-wrap items-center gap-2">
        <div className="flex rounded-xl bg-sage p-1">
          {PRODUCTS.map((p) => (
            <button
              key={p.key}
              type="button"
              onClick={() => setParam("product", p.key)}
              className={`rounded-lg px-3.5 py-1.5 text-sm font-medium transition-colors ${
                product === p.key
                  ? "bg-white text-forest-deep shadow-sm"
                  : "text-ink-soft hover:text-ink"
              }`}
            >
              {p.label}
            </button>
          ))}
        </div>
        <button
          type="button"
          onClick={() => rows.data && exportLeads(product, rows.data)}
          className="ml-auto inline-flex items-center gap-2 rounded-xl border border-line bg-white px-3 py-1.5 text-xs font-medium text-ink-soft hover:bg-sage"
        >
          <Download size={14} />
          Export CSV
        </button>
      </div>

      {summaryRow && (
        <div className="grid gap-3 sm:grid-cols-3">
          <Card>
            <div className="text-xs uppercase tracking-wide text-ink-muted">
              Eligible pool
            </div>
            <div className="text-2xl font-bold">{summaryRow.eligible_pool}</div>
          </Card>
          <button
            type="button"
            onClick={() => setParam("quadrant", "act_now")}
            className="rounded-2xl border border-line bg-white p-5 text-left shadow-sm transition-colors hover:bg-sage"
          >
            <div className="text-xs uppercase tracking-wide text-ink-muted">
              Act-now leads
            </div>
            <div className="text-2xl font-bold text-emerald">{summaryRow.act_now}</div>
            <div className="text-[11px] text-ink-muted">click to list only these</div>
          </button>
          <Card>
            <div className="text-xs uppercase tracking-wide text-ink-muted">
              Best repayable (shown)
            </div>
            <div className="text-2xl font-bold">{inr(shownRepayable)}</div>
            <div className="text-[11px] text-ink-muted">illustrative, not an offer</div>
          </Card>
        </div>
      )}

      <Card>
        <div className="mb-3 flex flex-wrap items-center gap-2 text-xs">
          <select
            value={quadrant}
            onChange={(e) => setParam("quadrant", e.target.value)}
            className="rounded-lg border border-line bg-white px-2 py-1.5"
          >
            <option value="">All quadrants</option>
            <option value="act_now">Act now</option>
            <option value="nurture">Nurture</option>
            <option value="downsell">Downsell</option>
            <option value="exclude">Exclude</option>
          </select>
          <select
            value={band}
            onChange={(e) => setParam("band", e.target.value)}
            className="rounded-lg border border-line bg-white px-2 py-1.5"
          >
            <option value="">All bands</option>
            <option value="high">High</option>
            <option value="medium">Medium</option>
            <option value="low">Low</option>
          </select>
          <select
            value={source}
            onChange={(e) => setParam("source", e.target.value)}
            className="rounded-lg border border-line bg-white px-2 py-1.5"
          >
            <option value="">All sources</option>
            <option value="seeded">Seeded</option>
            <option value="uploaded">Uploaded</option>
          </select>
          <label className="flex items-center gap-1 text-ink-soft">
            min decile
            <select
              value={minDecile}
              onChange={(e) =>
                setParam("min_decile", e.target.value === "0" ? "" : e.target.value)
              }
              className="rounded-lg border border-line bg-white px-2 py-1.5"
            >
              {Array.from({ length: 10 }, (_, i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </label>
        </div>

        {rows.loading ? (
          <Loading />
        ) : rows.error ? (
          <ErrorNote message={rows.error} />
        ) : (
          <DataTable
            columns={columns}
            rows={rows.data ?? []}
            rowKey={(r) => r.customer_id}
            onRowClick={openCustomer}
          />
        )}
      </Card>
    </div>
  );
}
