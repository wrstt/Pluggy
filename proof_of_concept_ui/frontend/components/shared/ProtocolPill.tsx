export function ProtocolPill(props: { protocol: "http" | "torrent" }) {
  const classes =
    props.protocol === "torrent"
      ? "bg-emerald-500/20 text-emerald-300"
      : "bg-sky-500/20 text-sky-300";
  return <span className={`rounded px-2 py-0.5 uppercase ${classes}`}>{props.protocol}</span>;
}
