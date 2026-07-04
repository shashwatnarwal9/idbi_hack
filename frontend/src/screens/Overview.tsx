import { PiggyBank, Users, Wallet } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { ErrorNote, Loading } from "../components/Feedback";
import { AssistantPromo } from "../components/overview/AssistantPromo";
import { ConfidenceFlowDonut } from "../components/overview/ConfidenceFlowDonut";
import { RecentProspectsTable } from "../components/overview/RecentProspectsTable";
import { StatRow, type OverviewStat } from "../components/overview/StatRow";
import type { OverviewSummary, RankedCustomer } from "../lib/apiTypes";
import { inr } from "../lib/format";
import { useApi } from "../lib/useApi";

export function Overview() {
  const navigate = useNavigate();
  const summary = useApi<OverviewSummary>("/overview/summary");
  const ranked = useApi<RankedCustomer[]>("/customers/ranked");

  if (summary.loading) return <Loading />;
  if (summary.error || !summary.data)
    return <ErrorNote message={summary.error ?? "no summary returned"} />;
  const s = summary.data;

  const uplift =
    s.avg_reconstructed !== null && s.avg_declared !== null
      ? s.avg_reconstructed - s.avg_declared
      : null;
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
      <StatRow stats={stats} />

      <div className="grid gap-5 lg:grid-cols-2">
        <AssistantPromo
          title="AI Prospecting Assistant"
          description="Rank the whole book by prospect score, filter by trust band, and open any profile."
          buttonLabel="Start Deep Analysis"
          onStart={() => navigate("/analysis")}
        />
        <ConfidenceFlowDonut split={bandSplit} />
      </div>

      {ranked.error ? (
        <ErrorNote message={ranked.error} />
      ) : (
        <RecentProspectsTable
          prospects={topProspects}
          onSelect={(p) => navigate(`/customers?id=${p.customerId}`)}
        />
      )}
    </div>
  );
}
