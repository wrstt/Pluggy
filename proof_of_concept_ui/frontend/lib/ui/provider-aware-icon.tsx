"use client";

import { useMemo, useState } from "react";
import { IntelligentIcon, type ProtocolKind } from "@/lib/ui/intelligent-icon";
import { providerFaviconUrl } from "@/lib/ui/provider-icons";

export function ProviderAwareIcon(props: {
  title: string;
  provider?: string;
  protocol?: ProtocolKind | string;
  size?: number;
}) {
  const size = props.size ?? 40;
  const [failed, setFailed] = useState(false);
  const iconUrl = useMemo(() => providerFaviconUrl(props.provider, Math.max(32, size * 2)), [props.provider, size]);

  if (!iconUrl || failed) {
    return (
      <IntelligentIcon title={props.title} provider={props.provider} protocol={props.protocol} size={size} />
    );
  }

  return (
    <span
      className="inline-flex items-center justify-center overflow-hidden border border-white/20 bg-white/10"
      style={{ width: size, height: size, borderRadius: Math.round(size * 0.26) }}
      title={`${props.provider ?? "provider"} icon`}
    >
      <img
        src={iconUrl}
        alt=""
        loading="lazy"
        width={Math.max(16, Math.round(size * 0.72))}
        height={Math.max(16, Math.round(size * 0.72))}
        className="opacity-95"
        onError={() => setFailed(true)}
      />
    </span>
  );
}
