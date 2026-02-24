export function SourceCard(props: { name: string; status: string }) {
  return (
    <article className="rounded-xl border border-white/10 bg-white/5 p-4">
      <div className="flex items-center justify-between">
        <h2 className="font-semibold">{props.name}</h2>
        <span className="rounded bg-black/30 px-2 py-1 text-xs text-zinc-300">{props.status}</span>
      </div>
      <p className="mt-2 text-sm text-zinc-400">Provider health and trust controls will live here.</p>
    </article>
  );
}
