import { TransferRow } from "@/components/transfer/TransferRow";

export function TransferLane(props: { title: string }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-4">
      <h2 className="mb-3 text-lg font-semibold">{props.title}</h2>
      <TransferRow name="Example Package" status={props.title} />
    </section>
  );
}
