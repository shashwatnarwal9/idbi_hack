import { CheckCircle2, TriangleAlert } from "lucide-react";

import type { ValidationFailure } from "../lib/apiTypes";
import { Card } from "./Card";

interface Props {
  failures: ValidationFailure[];
  title?: string;
  subtitle?: string;
  /** Shown (with a green check) when there are no failures. */
  allPassedMessage?: string;
  /** Optional footnote under the list (e.g. the soft-gate explanation). */
  footnote?: string;
}

const SEVERITY_STYLE: Record<string, { icon: typeof TriangleAlert; className: string }> = {
  hard: { icon: TriangleAlert, className: "text-negative" },
  soft: { icon: TriangleAlert, className: "text-amber" },
};

/**
 * Shared "needs attention" card. Renders a list of failed expectations
 * ({expectation_name, layer, detail, severity}), or an all-passed state when
 * the list is empty. Reused by the Validation page and by failed-gate upload
 * batches so a gate failure looks identical everywhere.
 */
export function ValidationFailuresCard({
  failures,
  title = "Needs attention",
  subtitle = "Checks that did not fully pass",
  allPassedMessage = "Every expectation passed — nothing flagged.",
  footnote,
}: Props) {
  return (
    <Card title={title} subtitle={subtitle}>
      {failures.length === 0 ? (
        <p className="flex items-center gap-2 py-4 text-sm text-ink-soft">
          <CheckCircle2 size={17} className="text-emerald" />
          {allPassedMessage}
        </p>
      ) : (
        <ul className="space-y-3">
          {failures.map((f, i) => {
            const sev = SEVERITY_STYLE[f.severity] ?? SEVERITY_STYLE.hard;
            const Icon = sev.icon;
            return (
              <li
                key={`${f.expectation_name}-${f.layer}-${i}`}
                className="flex items-start gap-3"
              >
                <Icon
                  size={17}
                  strokeWidth={2}
                  className={`mt-0.5 shrink-0 ${sev.className}`}
                />
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-xs text-ink">
                      {f.expectation_name}
                    </span>
                    <span className="rounded-full bg-sage px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-ink-muted">
                      {f.layer}
                    </span>
                  </div>
                  {f.detail && (
                    <div className="mt-0.5 text-sm text-ink-soft">{f.detail}</div>
                  )}
                </div>
              </li>
            );
          })}
        </ul>
      )}
      {footnote && (
        <p className="mt-4 rounded-xl bg-sage p-3 text-xs leading-relaxed text-ink-soft">
          {footnote}
        </p>
      )}
    </Card>
  );
}
