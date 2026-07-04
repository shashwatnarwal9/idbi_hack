import type { ReactNode } from "react";

interface SectionHeaderProps {
  /** Optional in-content heading. The page TITLE is owned by the Topbar
   * (single source), so pages pass only a description + actions here to avoid
   * rendering the title twice. */
  title?: string;
  description?: string;
  actions?: ReactNode;
}

export function SectionHeader({ title, description, actions }: SectionHeaderProps) {
  if (!title && !description && !actions) return null;
  return (
    <div className="mb-5 flex items-end justify-between gap-3">
      <div>
        {title && <h2 className="text-xl font-semibold">{title}</h2>}
        {description && <p className="text-sm text-ink-soft">{description}</p>}
      </div>
      {actions}
    </div>
  );
}
