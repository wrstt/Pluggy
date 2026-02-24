import { ProtocolPill } from "@/components/shared/ProtocolPill";

export function SourceRow(props: {
  title: string;
  protocol: "http" | "torrent";
  provider: string;
  size: string;
}) {
  return (
    <article className="mb-3 rounded-lg border border-white/10 bg-white/5 p-3 last:mb-0">
      <div className="flex items-center justify-between gap-2">
        <div>
          <h2 className="text-sm font-semibold">{props.title}</h2>
          <p className="text-xs text-zinc-400">{props.provider}</p>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <ProtocolPill protocol={props.protocol} />
          <span className="text-zinc-300">{props.size}</span>
          <button className="btn-primary">Send to RD</button>
        </div>
      </div>
    </article>
  );
}
