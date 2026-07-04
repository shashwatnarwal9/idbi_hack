import {
  CheckCircle2,
  Database,
  Gem,
  Layers,
  TriangleAlert,
  type LucideIcon,
} from "lucide-react";

import { Badge, type BadgeTone } from "../components/Badge";
import { Card } from "../components/Card";
import { SectionHeader } from "../components/SectionHeader";
import { StatCard } from "../components/StatCard";
import type { GateStatus } from "../mocks/types";
import { gateCards, historyBuckets, lastRun, validationLog } from "../mocks/pipeline";

const bands = historyBuckets.reduce(
  (acc, b) => ({
    high: acc.high + b.high,
    medium: acc.medium + b.medium,
    low: acc.low + b.low,
  }),
  { high: 0, medium: 0, low: 0 },
);
const totalBands = bands.high + bands.medium + bands.low;
const failed = validationLog.filter((r) => r.status === "FAIL").length;
const passed = lastRun.expectationsEvaluated - failed;
const cleanGates = gateCards.filter((g) => g.status === "passed").length;

const GATE_ICON: Record<string, LucideIcon> = {
  Bronze: Database,
  Silver: Layers,
  Gold: Gem,
};

const STATUS: Record<GateStatus, { tone: BadgeTone; label: string; icon: LucideIcon }> = {
  passed: { tone: "success", label: "Passed", icon: CheckCircle2 },
  warning: { tone: "warning", label: "Warning", icon: TriangleAlert },
  notrun: { tone: "neutral", label: "Not run", icon: TriangleAlert },
};

/** Great Expectations data-quality results — the key outcomes of the last run. */
export function Validation() {
  const flags = validationLog.filter((r) => r.status === "FAIL");

  return (
    <div className="space-y-5">
      <SectionHeader
        title="Validation"
        description={`Latest Great Expectations run · ${lastRun.timestamp}`}
      />

      <div className="grid gap-5 md:grid-cols-3">
        <StatCard
          label="Expectations passed"
          value={`${passed} / ${lastRun.expectationsEvaluated}`}
          hint="across bronze, silver and gold suites"
          icon={CheckCircle2}
        />
        <StatCard
          label="Data gates clean"
          value={`${cleanGates} / ${gateCards.length}`}
          hint="Bronze & Silver fully passed"
          icon={Layers}
        />
        <StatCard
          label="High-trust records"
          value={`${bands.high} / ${totalBands}`}
          hint={`${bands.medium} medium · ${bands.low} low`}
          icon={Gem}
        />
      </div>

      <div className="grid gap-5 md:grid-cols-3">
        {gateCards.map((gate) => {
          const s = STATUS[gate.status];
          const Icon = GATE_ICON[gate.layer] ?? Database;
          return (
            <Card key={gate.layer}>
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="rounded-xl bg-sage p-2.5 text-forest">
                    <Icon size={18} strokeWidth={1.8} />
                  </div>
                  <span className="text-base font-semibold">{gate.layer}</span>
                </div>
                <Badge tone={s.tone}>{s.label}</Badge>
              </div>
              <p className="mt-3 text-sm text-ink-soft">{gate.qualityDetail}</p>
            </Card>
          );
        })}
      </div>

      <Card
        title="Needs attention"
        subtitle="The only checks that did not fully pass in this run"
      >
        {flags.length === 0 ? (
          <p className="py-4 text-sm text-ink-soft">
            Every expectation passed — nothing flagged.
          </p>
        ) : (
          <ul className="space-y-3">
            {flags.map((row) => (
              <li key={row.expectation} className="flex items-start gap-3">
                <TriangleAlert
                  size={17}
                  strokeWidth={2}
                  className="mt-0.5 shrink-0 text-amber"
                />
                <div className="min-w-0">
                  <div className="font-mono text-xs text-ink">{row.expectation}</div>
                  <div className="mt-0.5 text-sm text-ink-soft">{row.impact}</div>
                </div>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-4 rounded-xl bg-sage p-3 text-xs leading-relaxed text-ink-soft">
          These are trust-tier checks, not hard failures: they do not stop the
          pipeline. They downgrade a customer's confidence band so a weaker
          estimate is never presented as high-trust.
        </p>
      </Card>
    </div>
  );
}
