import { BadgeCheck, Calendar, MapPin } from "lucide-react";

import { Badge } from "../Badge";

function initials(name: string): string {
  return name
    .split(" ")
    .map((part) => part[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();
}

interface ProfileHeaderProps {
  name: string;
  customerId: string;
  /** e.g. "Mar 2019"; pass "unavailable" when the source lacks it. */
  memberSince: string;
  location: string;
  occupation: string;
}

export function ProfileHeader({
  name,
  customerId,
  memberSince,
  location,
  occupation,
}: ProfileHeaderProps) {
  return (
    <section className="flex flex-wrap items-center gap-4 rounded-2xl border border-line bg-white p-5 shadow-sm">
      <div className="flex size-14 items-center justify-center rounded-full bg-mint text-lg font-semibold text-forest-deep">
        {initials(name)}
      </div>

      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2.5">
          <h2 className="text-lg font-semibold">{name}</h2>
          <span className="font-mono text-xs text-ink-muted">{customerId}</span>
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-soft">
          <span className="inline-flex items-center gap-1.5">
            <Calendar size={13} />
            Member since {memberSince}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <MapPin size={13} />
            {location}
          </span>
          <Badge tone="neutral">{occupation}</Badge>
        </div>
      </div>

      <span className="inline-flex items-center gap-1.5 rounded-full bg-mint px-3 py-1.5 text-xs font-semibold tracking-wide text-forest-deep">
        <BadgeCheck size={14} />
        PROFILE COMPLETE
      </span>
    </section>
  );
}
