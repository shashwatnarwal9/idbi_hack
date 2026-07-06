import { CheckCircle2, Search } from "lucide-react";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import { COLORS } from "../lib/colors";
import type { CustomerIntent, IntentBook } from "../lib/apiTypes";
import { inr } from "../lib/format";
import { useApi } from "../lib/useApi";
import type { ConfidenceBand } from "../mocks/types";

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

const PRODUCTS = ["personal", "auto", "home", "mortgage"] as const;

/** The signature 90% behavioural / 10% engagement stacked bar. */
function CompositionBar({ data }: { data: CustomerIntent }) {
  const split = data.composition.split;
  const b = split.find((s) => s.part === "behavioral")?.contribution ?? 0;
  const e = split.find((s) => s.part === "engagement")?.contribution ?? 0;
  const total = Math.max(b + e, 0.0001);
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-ink-muted">
        <span>Fused intent composition</span>
        <span>
          {data.engagement_used ? "90% behavioural · 10% engagement" : "behavioural only"}
        </span>
      </div>
      <div className="flex h-6 overflow-hidden rounded-lg">
        <div
          className="flex items-center justify-center bg-forest text-[10px] font-semibold text-white"
          style={{ width: `${(b / total) * 100}%` }}
          title={`behavioural ${b.toFixed(1)}`}
        >
          B {b.toFixed(0)}
        </div>
        {data.engagement_used && (
          <div
            className="flex items-center justify-center bg-emerald text-[10px] font-semibold text-white"
            style={{ width: `${(e / total) * 100}%` }}
            title={`engagement ${e.toFixed(1)}`}
          >
            E {e.toFixed(0)}
          </div>
        )}
      </div>
      {!data.engagement_used && (
        <p className="mt-1 text-xs text-amber">
          Engagement data unavailable — behavioural only.
        </p>
      )}
    </div>
  );
}

function CustomerIntentView({ id }: { id: string }) {
  const { data, loading, error } = useApi<CustomerIntent>(
    `/intent/${encodeURIComponent(id)}`,
  );
  if (loading) return <Loading />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const maxProduct = Math.max(...Object.values(data.per_product_intent), 1);

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-wrap items-center gap-3">
          <div>
            <div className="flex items-center gap-2">
              <span className="text-base font-semibold">{data.name}</span>
              <Badge tone={BAND_TONE[data.confidence_band]}>
                {data.confidence_band}
              </Badge>
              <Badge tone="brand">{QUADRANT_LABEL[data.quadrant] ?? data.quadrant}</Badge>
            </div>
            <div className="mt-0.5 font-mono text-xs text-ink-muted">
              {data.customer_id} · decile {data.intent_decile}
            </div>
          </div>
          <div className="ml-auto text-right">
            <div className="text-3xl font-bold text-forest-deep">
              {data.intent.toFixed(1)}
            </div>
            <div className="text-xs text-ink-muted">fused intent /100</div>
          </div>
        </div>
        <div className="mt-4">
          <CompositionBar data={data} />
        </div>
      </Card>

      <div className="grid gap-5 md:grid-cols-2">
        <Card title="Per-product intent" subtitle="Behavioural + event affinity">
          <div className="space-y-3">
            {PRODUCTS.map((p) => {
              const v = data.per_product_intent[p] ?? 0;
              return (
                <div key={p} className="flex items-center gap-3">
                  <span className="w-20 shrink-0 text-sm capitalize text-ink-soft">
                    {p}
                  </span>
                  <div className="h-2 flex-1 overflow-hidden rounded-full bg-sage">
                    <div
                      className="h-full rounded-full bg-forest"
                      style={{ width: `${(v / maxProduct) * 100}%` }}
                    />
                  </div>
                  <span className="w-12 shrink-0 text-right text-sm font-semibold">
                    {v.toFixed(0)}
                  </span>
                </div>
              );
            })}
          </div>
        </Card>

        <div className="space-y-5">
          <Card title="Best-fit loan" subtitle="Top eligible product by intent">
            {data.best_fit_product ? (
              <div>
                <div className="flex items-center gap-2 text-lg font-semibold capitalize">
                  <CheckCircle2 size={18} className="text-emerald" />
                  {data.best_fit_product}
                </div>
                <p className="mt-1 text-sm text-ink-soft">
                  {data.best_fit_reason ??
                    "Top per-product intent among products this customer qualifies for."}
                </p>
              </div>
            ) : (
              <p className="text-sm text-ink-muted">
                {data.best_fit_reason ?? "No product passes the eligibility gate."}
              </p>
            )}
          </Card>

          {data.best_repayable && (
            <Card title="Best repayable" subtitle="Affordable, capped by surplus & FOIR">
              <div className="flex items-baseline justify-between">
                <span className="text-sm text-ink-soft">Affordable EMI</span>
                <span className="text-lg font-bold text-forest-deep">
                  {inr(data.best_repayable.affordable_emi)}/mo
                </span>
              </div>
              <div className="mt-1 flex items-baseline justify-between">
                <span className="text-sm text-ink-soft">
                  Max principal @ {data.best_repayable.annual_rate_pct}% ·{" "}
                  {data.best_repayable.tenure_months}mo
                </span>
                <span className="font-semibold">
                  {inr(data.best_repayable.max_principal)}
                </span>
              </div>
              <p className="mt-2 text-[11px] text-ink-muted">{data.disclaimer}</p>
            </Card>
          )}
        </div>
      </div>

      {data.engagement && (
        <Card title="Engagement" subtitle="Marketing events (10% of intent)">
          <div className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div>
              <div className="text-xs text-ink-muted">Last event</div>
              <div className="font-medium">{data.engagement.last_event_type}</div>
            </div>
            <div>
              <div className="text-xs text-ink-muted">Sessions (90d)</div>
              <div className="font-medium">{data.engagement.sessions_90d}</div>
            </div>
            <div>
              <div className="text-xs text-ink-muted">Strongest action</div>
              <div className="font-medium">{data.engagement.strongest_action}</div>
            </div>
            <div>
              <div className="text-xs text-ink-muted">Offer click rate</div>
              <div className="font-medium">
                {Math.round(data.engagement.offer_click_rate * 100)}%
              </div>
            </div>
          </div>
        </Card>
      )}
    </div>
  );
}

const QUADRANT_COLOR: Record<string, string> = {
  act_now: COLORS.emerald,
  nurture: COLORS.forest,
  downsell: COLORS.amber,
  exclude: COLORS.negative,
};

function BookView({ onPick }: { onPick: (id: string) => void }) {
  const { data, loading, error } = useApi<IntentBook>("/intent/book");
  const [cutoff, setCutoff] = useState(0);
  if (loading) return <Loading />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const scatter = data.points
    .filter((p) => p.capacity !== null)
    .map((p) => ({ ...p, x: (p.capacity ?? 0) * 100, y: p.intent }));
  const pool = data.points.filter((p) => p.intent_decile >= cutoff).length;

  return (
    <div className="space-y-5">
      <div className="grid gap-3 sm:grid-cols-4">
        {(["act_now", "nurture", "downsell", "exclude"] as const).map((q) => (
          <Card key={q}>
            <div className="text-xs uppercase tracking-wide text-ink-muted">
              {QUADRANT_LABEL[q]}
            </div>
            <div className="text-2xl font-bold" style={{ color: QUADRANT_COLOR[q] }}>
              {data.quadrants[q] ?? 0}
            </div>
          </Card>
        ))}
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Capacity × intent" subtitle="Click a point to open the customer">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 8, bottom: 20, left: 0 }}>
                <XAxis
                  type="number"
                  dataKey="x"
                  name="capacity"
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                  label={{ value: "capacity", position: "insideBottom", offset: -8, fontSize: 11 }}
                />
                <YAxis
                  type="number"
                  dataKey="y"
                  name="intent"
                  domain={[0, 100]}
                  tick={{ fontSize: 11 }}
                />
                <Tooltip cursor={{ strokeDasharray: "3 3" }} />
                <Scatter
                  data={scatter}
                  onClick={(pt) => {
                    const cid = (pt as unknown as { customer_id?: string })
                      .customer_id;
                    if (cid) onPick(cid);
                  }}
                >
                  {scatter.map((p) => (
                    <Cell
                      key={p.customer_id}
                      fill={QUADRANT_COLOR[p.quadrant] ?? COLORS.forest}
                      cursor="pointer"
                    />
                  ))}
                </Scatter>
              </ScatterChart>
            </ResponsiveContainer>
          </div>
        </Card>

        <Card title="Intent deciles" subtitle="Customers per intent decile">
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.deciles} margin={{ top: 8, right: 8, bottom: 20, left: 0 }}>
                <XAxis dataKey="decile" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Bar dataKey="count" fill={COLORS.forest} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="mt-3">
            <label className="text-xs text-ink-soft">
              Decile cutoff: ≥ {cutoff} → <strong>{pool}</strong> customers in pool
            </label>
            <input
              type="range"
              min={0}
              max={9}
              value={cutoff}
              onChange={(e) => setCutoff(Number(e.target.value))}
              className="mt-1 w-full"
            />
          </div>
        </Card>
      </div>
    </div>
  );
}

export function Intent() {
  const [params, setParams] = useSearchParams();
  const id = params.get("id");
  const [query, setQuery] = useState(id ?? "");

  const open = (cid: string) => setParams({ id: cid });

  return (
    <div className="space-y-5">
      <SectionHeader description="Fused purchase intent — 90% behavioural, 10% engagement" />

      <Card>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex flex-1 items-center gap-2 rounded-xl border border-line bg-cream px-3 py-2">
            <Search size={15} className="text-ink-muted" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && query.trim() && open(query.trim())}
              placeholder="Open a customer by id (e.g. CUST00001)…"
              className="w-full bg-transparent text-sm outline-none placeholder:text-ink-muted"
            />
          </label>
          <button
            type="button"
            onClick={() => query.trim() && open(query.trim())}
            className="rounded-xl bg-forest px-4 py-2 text-sm font-semibold text-white hover:bg-forest-deep"
          >
            View intent
          </button>
          {id && (
            <button
              type="button"
              onClick={() => setParams({})}
              className="rounded-xl border border-line bg-white px-4 py-2 text-sm font-medium text-ink-soft hover:bg-sage"
            >
              Book view
            </button>
          )}
        </div>
      </Card>

      {id ? <CustomerIntentView id={id} /> : <BookView onPick={open} />}
    </div>
  );
}
