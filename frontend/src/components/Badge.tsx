import type { ReactNode } from "react";

export type BadgeTone = "success" | "warning" | "danger" | "neutral" | "brand";

const TONE_CLASSES: Record<BadgeTone, string> = {
  success: "bg-mint text-forest-deep",
  warning: "bg-amber/15 text-amber",
  danger: "bg-negative/10 text-negative",
  neutral: "bg-sage text-ink-soft",
  brand: "bg-forest text-white",
};

interface BadgeProps {
  tone?: BadgeTone;
  children: ReactNode;
}

export function Badge({ tone = "neutral", children }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]}`}
    >
      {children}
    </span>
  );
}
