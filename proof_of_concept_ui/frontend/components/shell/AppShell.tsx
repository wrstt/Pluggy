"use client";

import Link from "next/link";
import { GlobalSearch } from "@/components/search/GlobalSearch";
import { usePathname, useRouter } from "next/navigation";

const navItems = [
  { href: "/", label: "Home" },
  { href: "/search", label: "Search" },
  { href: "/transfers", label: "Transfers" },
  { href: "/sources", label: "Sources" },
  { href: "/history", label: "History" },
  { href: "/settings", label: "Settings" }
];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();

  return (
    <div className="mx-auto min-h-screen max-w-7xl px-4 py-4">
      <header className="sticky top-0 z-20 mb-6 rounded-2xl border border-white/20 bg-white/10 p-4 shadow-[0_10px_35px_rgba(4,8,20,0.45)] backdrop-blur-2xl">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
          <div className="inline-flex h-12 items-center rounded-md px-1">
            <img
              src="/brand/pluggy-lockup-horizontal.svg"
              alt="Pluggy"
              className="h-7 w-auto object-contain opacity-95 drop-shadow-[0_2px_10px_rgba(0,0,0,0.35)]"
            />
          </div>
          <div className="flex w-full flex-col gap-3 lg:flex-row lg:items-center lg:justify-end">
            <nav className="flex flex-wrap items-center gap-2 text-sm text-zinc-200">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className="inline-flex h-9 items-center rounded-md border border-white/20 bg-black/25 px-3 text-sm font-medium transition hover:border-white/35 hover:bg-white/20"
                >
                  {item.label}
                </Link>
              ))}
              <Link
                href="/switch"
                className="inline-flex h-9 items-center rounded-md border border-white/20 bg-black/25 px-3 text-sm font-medium transition hover:border-white/35 hover:bg-white/20"
              >
                Switch
              </Link>
            </nav>
            <div className="w-full lg:w-auto lg:min-w-[24rem]">
              <GlobalSearch />
            </div>
          </div>
        </div>
      </header>
      <div key={pathname} className="page-fade-in">
        {children}
      </div>
    </div>
  );
}
