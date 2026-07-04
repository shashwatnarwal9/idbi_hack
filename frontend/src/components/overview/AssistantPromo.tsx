import { ArrowRight, Sparkles } from "lucide-react";

interface AssistantPromoProps {
  title: string;
  description: string;
  buttonLabel: string;
  onStart?: () => void;
}

/** Green promo card for the prospecting assistant with its CTA button. */
export function AssistantPromo({
  title,
  description,
  buttonLabel,
  onStart,
}: AssistantPromoProps) {
  return (
    <section className="rounded-2xl bg-forest p-5 text-white shadow-sm">
      <div className="mb-3 inline-flex rounded-xl bg-white/10 p-2.5">
        <Sparkles size={18} strokeWidth={1.8} className="text-mint" />
      </div>
      <h2 className="text-base font-semibold">{title}</h2>
      <p className="mt-1.5 text-sm leading-relaxed text-white/70">{description}</p>
      <button
        type="button"
        onClick={onStart}
        className="mt-4 inline-flex items-center gap-2 rounded-xl bg-mint px-4 py-2.5 text-sm font-semibold text-forest-deep transition-colors hover:bg-white"
      >
        {buttonLabel}
        <ArrowRight size={15} strokeWidth={2} />
      </button>
    </section>
  );
}
