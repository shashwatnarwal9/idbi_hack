import type { ReactNode } from "react";

interface CardProps {
  title?: string;
  subtitle?: string;
  actions?: ReactNode;
  /** "mint" renders the soft highlighted variant used for callout cards. */
  tone?: "default" | "mint";
  className?: string;
  children: ReactNode;
}

export function Card({
  title,
  subtitle,
  actions,
  tone = "default",
  className = "",
  children,
}: CardProps) {
  const surface =
    tone === "mint" ? "bg-mint border-transparent" : "bg-white border-line";
  return (
    <section className={`rounded-2xl border ${surface} p-5 shadow-sm ${className}`}>
      {(title || actions) && (
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="text-sm font-semibold">{title}</h2>}
            {subtitle && (
              <p className="mt-0.5 text-xs text-ink-muted">{subtitle}</p>
            )}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}
