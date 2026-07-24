import {
  Flame,
  PiggyBank,
  PlayCircle,
  UploadCloud,
  Users,
  Wallet,
} from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { AssistantPromo } from "../components/overview/AssistantPromo";
import { ConfidenceFlowDonut } from "../components/overview/ConfidenceFlowDonut";
import { RecentProspectsTable } from "../components/overview/RecentProspectsTable";
import { StatRow, type OverviewStat } from "../components/overview/StatRow";
import { UploadModal } from "../components/UploadModal";
import type {
  IntentBook,
  LeadsSummary,
  OverviewSummary,
  RankedCustomer,
} from "../lib/apiTypes";
import { inr } from "../lib/format";
import { useApi } from "../lib/useApi";

const QUADRANT_LABEL: Record<string, string> = {
  act_now: "Act now",
  nurture: "Nurture",
  downsell: "Downsell",
  exclude: "Exclude",
};

export const DEMO_URL =
  "https://drive.google.com/drive/folders/1IyNEhb1n7vADiheEQYjXrzcvJkR-NkQx?usp=sharing";

export function Overview() {
  const navigate = useNavigate();
  const [uploadOpen, setUploadOpen] = useState(false);
  const summary = useApi<OverviewSummary>("/overview/summary");
  const ranked = useApi<RankedCustomer[]>("/customers/ranked");
  const book = useApi<IntentBook>("/intent/book");
  const leadsSummary = useApi<LeadsSummary>("/leads/summary");

  if (summary.loading) return <Loading />;
  if (summary.error || !summary.data)
    return <ErrorNote message={summary.error ?? "no summary returned"} />;
  const s = summary.data;

  const uplift =
    s.avg_reconstructed !== null && s.avg_declared !== null
      ? s.avg_reconstructed - s.avg_declared
      : null;
  const actNow = (leadsSummary.data?.products ?? []).reduce(
    (sum, p) => sum + p.act_now,
    0,
  );
  const stats: OverviewStat[] = [
    {
      label: "Total Customers",
      value: s.customers.toLocaleString("en-IN"),
      sub: `${s.bands.high} with high-trust estimates`,
      trendKind: "neutral",
      icon: Users,
    },
    {
      label: "Avg Monthly Income",
      value: s.avg_reconstructed !== null ? inr(s.avg_reconstructed) : "unavailable",
      sub:
        s.avg_declared !== null
          ? `vs ${inr(s.avg_declared)} declared`
          : "declared avg unavailable",
      trend: uplift !== null ? `₹${uplift.toLocaleString("en-IN")} uplift found` : undefined,
      trendKind: uplift !== null && uplift > 0 ? "positive" : "neutral",
      icon: Wallet,
    },
    {
      label: "Median Surplus",
      value: s.median_surplus !== null ? inr(s.median_surplus) : "unavailable",
      sub: "after essentials, EMI & buffer",
      trendKind: "neutral",
      icon: PiggyBank,
    },
    {
      label: "Act-Now Leads",
      value: actNow.toLocaleString("en-IN"),
      sub: "high capacity × high intent",
      trendKind: actNow > 0 ? "positive" : "neutral",
      icon: Flame,
    },
  ];

  const topProspects = (ranked.data ?? []).slice(0, 5).map((r) => ({
    customerId: r.customer_id,
    name: r.name,
    reviewed: r.reviewed,
    score: Math.round(r.score * 100),
    band: r.band,
    reasons: r.reasons.slice(0, 2).map((reason) => ({
      feature: reason.feature,
      direction: reason.shap > 0 ? ("up" as const) : ("down" as const),
    })),
  }));

  const bandSplit = (["high", "medium", "low"] as const).map((band) => ({
    band,
    count: s.bands[band],
  }));

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <p className="text-sm text-ink-soft">
          Book health, intent distribution and lead pipeline at a glance.
        </p>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setUploadOpen(true)}
            className="inline-flex items-center gap-2 rounded-xl bg-forest px-4 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-forest-deep"
          >
            <UploadCloud size={16} />
            Upload &amp; Analyze
          </button>
          <a
            href={DEMO_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-2 rounded-xl bg-gradient-to-r from-forest to-amber-400 px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90"
          >
            <PlayCircle size={16} />
            See demo
          </a>
        </div>
      </div>

      <StatRow stats={stats} />

      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Intent quadrants"
          subtitle="Capacity × intent, click a quadrant to list its customers"
        >
          {book.data ? (
            <div className="grid grid-cols-2 gap-3">
              {(["act_now", "nurture", "downsell", "exclude"] as const).map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() =>
                    navigate(`/quadrant/${q}`, {
                      state: { from: "/", fromLabel: "Overview" },
                    })
                  }
                  className="rounded-xl border border-line bg-white p-3 text-left hover:bg-sage"
                >
                  <div className="text-xs uppercase tracking-wide text-ink-muted">
                    {QUADRANT_LABEL[q]}
                  </div>
                  <div className="text-2xl font-bold">
                    {book.data?.quadrants[q] ?? 0}
                  </div>
                </button>
              ))}
            </div>
          ) : (
            <Loading />
          )}
        </Card>
        <ConfidenceFlowDonut split={bandSplit} />
      </div>

      <AssistantPromo
        title="Customer Rankings"
        description="Rank the whole book by prospect score, filter by trust band, and open any profile."
        buttonLabel="Start Deep Analysis"
        onStart={() => navigate("/analysis")}
      />

      {ranked.error ? (
        <ErrorNote message={ranked.error} />
      ) : (
        <RecentProspectsTable
          prospects={topProspects}
          onSelect={(p) => navigate(`/customers?id=${p.customerId}`)}
        />
      )}

      {uploadOpen && <UploadModal onClose={() => setUploadOpen(false)} />}
    </div>
  );
}
