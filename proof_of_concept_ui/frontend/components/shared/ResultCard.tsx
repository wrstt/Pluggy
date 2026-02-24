import Link from "next/link";
import { ProviderAwareIcon } from "@/lib/ui/provider-aware-icon";

export function ResultCard(props: {
  title: string;
  subtitle: string;
  protocol: "http" | "torrent";
  provider?: string;
  itemId?: string;
  sourceResultId?: string;
  queueStatus?: string;
  onSendToRd?: (sourceResultId: string) => void;
  sending?: boolean;
}) {
  const buttonLabel = props.sending
    ? "Sending…"
    : props.queueStatus === "completed"
    ? "Done"
    : props.queueStatus === "downloading" || props.queueStatus === "paused"
    ? "In Transfer"
    : props.queueStatus === "queued" || props.queueStatus === "resolving"
    ? "Queued"
    : "Send to RD";
  const sendDisabled = props.sending || Boolean(props.queueStatus) || !props.sourceResultId;

  return (
    <article className="motion-soft group rounded-2xl border border-white/15 bg-white/10 p-4 shadow-[0_8px_30px_rgba(6,11,19,0.35)] backdrop-blur-xl transition hover:-translate-y-1 hover:border-white/25">
      <div className="mb-3 flex items-center gap-3 rounded-xl border border-white/20 bg-gradient-to-br from-white/20 via-white/5 to-black/10 p-3">
        <ProviderAwareIcon title={props.title} provider={props.provider} protocol={props.protocol} size={46} />
        <div className="min-w-0">
          <h3 className="truncate font-semibold">{props.title}</h3>
          <p className="truncate text-xs text-zinc-300">{props.provider ?? "Source"}</p>
        </div>
      </div>
      <div className="mb-2 flex items-center justify-between">
        <span />
        <span className="rounded-md border border-white/20 bg-black/30 px-2 py-0.5 text-xs uppercase text-zinc-200">
          {props.protocol}
        </span>
      </div>
      <p className="text-sm text-zinc-300">{props.subtitle}</p>
      <div className="mt-3 flex items-center gap-2">
        {props.itemId ? (
          <Link
            href={`/item/${encodeURIComponent(props.itemId)}`}
            className="inline-block rounded-md border border-white/20 bg-white/10 px-2 py-1 text-xs text-zinc-100 transition hover:bg-white/20"
          >
            Open Item
          </Link>
        ) : null}
        <button
          onClick={() => (props.sourceResultId ? props.onSendToRd?.(props.sourceResultId) : null)}
          disabled={sendDisabled}
          className={`px-2 py-1 text-xs ${sendDisabled ? "btn-secondary opacity-90" : "btn-primary"}`}
        >
          {buttonLabel}
        </button>
      </div>
    </article>
  );
}
