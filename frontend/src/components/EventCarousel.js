import { CompactEventCard } from "@/components/CompactEventCard";

/**
 * Horizontal, snap-scrolling row of CompactEventCard.
 * Used above the main feed for "Top del finde", "Lo que va tu grupo", "Descubre géneros".
 */
export function EventCarousel({ title, subtitle, icon: Icon, events, testId }) {
  if (!events || events.length === 0) return null;
  return (
    <section className="mb-1" data-testid={testId}>
      <div className="px-5 pb-2 flex items-baseline justify-between">
        <div className="flex items-center gap-2">
          {Icon && <Icon className="w-4 h-4 text-qv-primary" />}
          <h2 className="font-display text-lg font-bold tracking-tight">{title}</h2>
        </div>
        {subtitle && <p className="text-white/40 text-xs">{subtitle}</p>}
      </div>
      <div className="flex gap-3 overflow-x-auto hide-scrollbar snap-x snap-mandatory px-5 pb-3">
        {events.map((ev, i) => (
          <div key={ev.id} className="snap-start">
            <CompactEventCard event={ev} index={i} width={160} />
          </div>
        ))}
      </div>
    </section>
  );
}
