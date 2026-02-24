import type { CSSProperties } from "react";

export type ProtocolKind = "http" | "torrent";
export type IconKind =
  | "vst"
  | "audio"
  | "windows"
  | "mac"
  | "plugin"
  | "developer"
  | "security"
  | "download"
  | "torrent"
  | "generic";

const KEYWORDS: Array<{ kind: IconKind; terms: string[] }> = [
  { kind: "vst", terms: ["vst", "vst3", "kontakt", "serum", "omnisphere", "plugin alliance"] },
  { kind: "audio", terms: ["ableton", "cubase", "fl studio", "audio", "producer", "synth"] },
  { kind: "windows", terms: ["windows", "win", "win64", "exe", "msi"] },
  { kind: "mac", terms: ["mac", "macos", "osx", "dmg", "pkg"] },
  { kind: "developer", terms: ["sdk", "dev", "developer", "code", "compiler", "terminal"] },
  { kind: "security", terms: ["security", "antivirus", "vpn", "firewall", "defender", "encrypt"] },
  { kind: "plugin", terms: ["plugin", "extension", "addon", "add-on"] },
  { kind: "download", terms: ["installer", "setup", "portable", "release", "download"] }
];

function hashText(input: string) {
  let h = 0;
  for (let i = 0; i < input.length; i += 1) {
    h = (h * 31 + input.charCodeAt(i)) >>> 0;
  }
  return h;
}

export function inferIconKind(input: {
  title?: string;
  provider?: string;
  protocol?: ProtocolKind | string;
}): IconKind {
  const title = (input.title ?? "").toLowerCase();
  const provider = (input.provider ?? "").toLowerCase();

  for (const row of KEYWORDS) {
    if (row.terms.some((term) => title.includes(term))) {
      return row.kind;
    }
  }

  if (provider.includes("open") || provider.includes("directory")) {
    return "download";
  }

  if ((input.protocol ?? "").toLowerCase() === "torrent") {
    return "torrent";
  }

  return "generic";
}

type Palette = {
  bg: string;
  fg: string;
  ring: string;
};

function paletteForKind(kind: IconKind): Palette {
  switch (kind) {
    case "vst":
      return { bg: "linear-gradient(135deg,#34d399,#0ea5e9)", fg: "#06241c", ring: "rgba(16,185,129,0.55)" };
    case "audio":
      return { bg: "linear-gradient(135deg,#22d3ee,#3b82f6)", fg: "#04152b", ring: "rgba(34,211,238,0.55)" };
    case "windows":
      return { bg: "linear-gradient(135deg,#60a5fa,#2563eb)", fg: "#031430", ring: "rgba(59,130,246,0.55)" };
    case "mac":
      return { bg: "linear-gradient(135deg,#f8fafc,#cbd5e1)", fg: "#111827", ring: "rgba(203,213,225,0.65)" };
    case "plugin":
      return { bg: "linear-gradient(135deg,#a78bfa,#60a5fa)", fg: "#120a2e", ring: "rgba(167,139,250,0.55)" };
    case "developer":
      return { bg: "linear-gradient(135deg,#f59e0b,#f97316)", fg: "#2b1303", ring: "rgba(249,115,22,0.6)" };
    case "security":
      return { bg: "linear-gradient(135deg,#4ade80,#22c55e)", fg: "#03240f", ring: "rgba(34,197,94,0.55)" };
    case "download":
      return { bg: "linear-gradient(135deg,#93c5fd,#38bdf8)", fg: "#07223c", ring: "rgba(56,189,248,0.55)" };
    case "torrent":
      return { bg: "linear-gradient(135deg,#10b981,#34d399)", fg: "#022417", ring: "rgba(52,211,153,0.55)" };
    default:
      return { bg: "linear-gradient(135deg,#cbd5e1,#64748b)", fg: "#0f172a", ring: "rgba(148,163,184,0.55)" };
  }
}

function glyphForKind(kind: IconKind): string {
  switch (kind) {
    case "vst":
      return "~";
    case "audio":
      return "A";
    case "windows":
      return "W";
    case "mac":
      return "M";
    case "plugin":
      return "P";
    case "developer":
      return "D";
    case "security":
      return "S";
    case "download":
      return "L";
    case "torrent":
      return "T";
    default:
      return "R";
  }
}

export function IntelligentIcon(props: {
  title: string;
  provider?: string;
  protocol?: ProtocolKind | string;
  size?: number;
}) {
  const size = props.size ?? 40;
  const kind = inferIconKind({ title: props.title, provider: props.provider, protocol: props.protocol });
  const palette = paletteForKind(kind);
  const token = hashText(`${props.title}|${props.provider ?? ""}|${kind}`) % 1000;
  const glow = 12 + (token % 8);

  const style: CSSProperties = {
    width: size,
    height: size,
    borderRadius: Math.round(size * 0.26),
    background: palette.bg,
    color: palette.fg,
    boxShadow: `0 0 ${glow}px ${palette.ring}`,
    border: "1px solid rgba(255,255,255,0.24)",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    fontWeight: 800,
    fontSize: Math.max(12, Math.round(size * 0.36)),
    letterSpacing: "0.02em",
    userSelect: "none"
  };

  return (
    <span style={style} title={`${kind} icon`} aria-label={`${kind} icon`}>
      {glyphForKind(kind)}
    </span>
  );
}
