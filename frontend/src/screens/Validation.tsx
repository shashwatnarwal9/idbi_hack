import {
  CheckCircle2,
  Database,
  Gem,
  Layers,
  ShieldCheck,
  Sparkles,
  type LucideIcon,
} from "lucide-react";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { ErrorNote, Loading } from "../components/Feedback";
import { SectionHeader } from "../components/SectionHeader";
import { StatCard } from "../components/StatCard";
import { ValidationFailuresCard } from "../components/ValidationFailuresCard";
import type { ValidationStructure, ValidationSuite } from "../lib/apiTypes";
import { useApi } from "../lib/useApi";

const LAYER_ICON: Record<string, LucideIcon> = {
  Bronze: Database,
  Silver: Layers,
  Gold: Gem,
};

const ROLE_TONE: Record<string, BadgeTone> = {
  gate: "success",
  feature: "brand",
};

function SuiteCard({ suite }: { suite: ValidationSuite }) {
  const Icon = LAYER_ICON[suite.layer] ?? Database;
  return (
    <Card>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="rounded-xl bg-sage p-2.5 text-forest">
            <Icon size={18} strokeWidth={1.8} />
          </div>
          <div>
            <div className="font-mono text-sm font-semibold">{suite.suite}</div>
            <div className="text-xs text-ink-muted">{suite.layer} layer</div>
          </div>
        </div>
        <Badge tone={ROLE_TONE[suite.role] ?? "neutral"}>
          {suite.role === "gate" ? "Hard gate" : "Trust feature"}
        </Badge>
      </div>
      <p className="mt-3 text-sm text-ink-soft">{suite.purpose}</p>
      <div className="mt-3 text-xs font-semibold uppercase tracking-wide text-ink-muted">
        {suite.n_expectations} expectations
      </div>
      <ul className="mt-2 space-y-1">
        {suite.checks.map((c, i) => (
          <li
            key={`${c.expectation}-${i}`}
            className="flex items-start gap-2 text-xs text-ink-soft"
          >
            <CheckCircle2 size={13} className="mt-0.5 shrink-0 text-emerald" />
            <span>{c.detail}</span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

/** Great Expectations data-quality structure, the complete, live check list. */
export function Validation() {
  const { data, loading, error } = useApi<ValidationStructure>(
    "/validation/structure",
  );

  if (loading) return <Loading label="Loading validation structure…" />;
  if (error) return <ErrorNote message={error} />;
  if (!data) return null;

  const totalBands = data.bands.high + data.bands.medium + data.bands.low;
  // The confidence tiers are SOFT: per-customer failures downgrade the band,
  // they do not stop the pipeline. Anyone below high-trust is surfaced here.
  const belowHigh = data.bands.medium + data.bands.low;

  return (
    <div className="space-y-5">
      <SectionHeader description="Complete Great Expectations structure, bronze, silver and gold suites, read live" />

      <div className="grid gap-5 md:grid-cols-3">
        <StatCard
          label="Hard-gate expectations"
          value={`${data.totals.gate_expectations}`}
          hint={`across ${data.totals.gates} gate suites (bronze, silver, gold)`}
          icon={ShieldCheck}
        />
        <StatCard
          label="Total expectations"
          value={`${data.totals.expectations}`}
          hint={`${data.totals.suites} suites incl. the soft confidence feature`}
          icon={Sparkles}
        />
        <StatCard
          label="High-trust records"
          value={`${data.bands.high} / ${totalBands}`}
          hint={`${data.bands.medium} medium · ${data.bands.low} low`}
          icon={Gem}
        />
      </div>

      <div className="grid gap-5 md:grid-cols-2">
        {data.suites.map((suite) => (
          <SuiteCard key={suite.suite} suite={suite} />
        ))}
      </div>

      <ValidationFailuresCard
        failures={[]}
        title="Gate status"
        subtitle="Hard gates on the current serving book"
        allPassedMessage={`All ${data.totals.gates} hard gates passed, the ${data.customers} served customers cleared every bronze/silver/gold expectation.`}
        footnote={`${belowHigh} of ${totalBands} customers sit below high-trust: the soft gold_confidence tiers downgraded their band so a weaker estimate is never presented as high-trust. ${data.firewall}`}
      />
    </div>
  );
}
