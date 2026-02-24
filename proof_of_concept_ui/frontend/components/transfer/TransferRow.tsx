export function TransferRow(props: { name: string; status: string }) {
  return (
    <div className="flex items-center justify-between rounded-md border border-white/10 bg-black/30 p-2 text-sm">
      <span>{props.name}</span>
      <span className="text-zinc-300">{props.status}</span>
    </div>
  );
}
