import { ProviderAwareIcon } from "@/lib/ui/provider-aware-icon";

export function ItemHeader(props: { title: string; aliases: string[] }) {
  return (
    <section className="rounded-xl border border-white/10 bg-white/5 p-5">
      <div className="flex items-center gap-3">
        <ProviderAwareIcon title={props.title} size={42} />
        <h1 className="text-2xl font-semibold">{props.title}</h1>
      </div>
      <p className="mt-1 text-sm text-zinc-300">Aliases: {props.aliases.join(", ")}</p>
    </section>
  );
}
