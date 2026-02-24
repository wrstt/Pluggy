import { ResultCard } from "@/components/shared/ResultCard";

type RailItem = {
  id: string;
  title: string;
  provider?: string;
  subtitle: string;
  protocol: "http" | "torrent";
  sourceResultId?: string;
};

export function Rail(props: {
  title: string;
  items: RailItem[];
  sendingId?: string | null;
  queuedBySourceId?: Record<string, string>;
  onSendToRd?: (sourceResultId: string) => void;
}) {
  return (
    <section className="space-y-3">
      <h2 className="text-xl font-semibold">{props.title}</h2>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {props.items.map((item) => (
          <ResultCard
            key={item.id}
            title={item.title}
            provider={item.provider}
            subtitle={item.subtitle}
            protocol={item.protocol}
            itemId={item.id}
            sourceResultId={item.sourceResultId}
            queueStatus={item.sourceResultId ? props.queuedBySourceId?.[item.sourceResultId] : undefined}
            onSendToRd={props.onSendToRd}
            sending={props.sendingId === item.sourceResultId}
          />
        ))}
        {props.items.length === 0 ? (
          <p className="text-sm text-zinc-300">No ranked results yet for this rail.</p>
        ) : null}
      </div>
    </section>
  );
}
