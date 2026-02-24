"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export function GlobalSearch() {
  const router = useRouter();
  const [query, setQuery] = useState("");

  return (
    <form
      className="flex w-full max-w-xl items-center gap-2"
      onSubmit={(event) => {
        event.preventDefault();
        const value = query.trim();
        if (!value) {
          return;
        }
        const nonce = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        router.push(`/search?q=${encodeURIComponent(value)}&r=${encodeURIComponent(nonce)}`);
      }}
    >
      <input
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        placeholder="Search apps, packages, releases"
        className="h-9 w-full rounded-lg border border-white/15 bg-black/25 px-3 text-sm font-medium outline-none ring-0 placeholder:text-zinc-400 focus:border-white/30"
      />
      <button
        type="submit"
        className="inline-flex h-9 items-center rounded-lg bg-[var(--accent-primary)] px-3 text-sm font-semibold tracking-tight text-black"
      >
        Search
      </button>
    </form>
  );
}
