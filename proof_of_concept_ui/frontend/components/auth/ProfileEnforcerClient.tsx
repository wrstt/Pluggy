"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";
import { DEFAULT_THEME_ID } from "@/lib/theme/presets";

export function ProfileEnforcerClient() {
  const pathname = usePathname();

  useEffect(() => {
    // Avoid loops on auth/profile pages, and do not enforce for static assets.
    if (!pathname || pathname.startsWith("/auth") || pathname.startsWith("/profiles")) return;

    let cancelled = false;
    (async () => {
      try {
        const resp = await fetch("/api/auth/status", { cache: "no-store" });
        const payload = await resp.json().catch(() => ({}));
        if (cancelled) return;

        if (!payload?.authenticated) {
          window.location.assign(`/auth?next=${encodeURIComponent(pathname)}`);
          return;
        }
        if (!payload?.profileId) {
          window.location.assign("/profiles");
          return;
        }

        // Apply per-profile theme (stored server-side on profile row; local fallback allowed).
        try {
          const profileId = String(payload.profileId || "");
          const profiles = Array.isArray(payload.profiles) ? payload.profiles : [];
          const matched = profiles.find((p: any) => String(p?.id || "") === profileId);
          const localKey = `pluggy:theme:${profileId}`;
          const localTheme = window.localStorage.getItem(localKey) || "";
          const serverTheme = String(matched?.themeId || "");
          const theme = serverTheme || localTheme || DEFAULT_THEME_ID;
          document.documentElement.setAttribute("data-theme", theme);
          window.localStorage.setItem(localKey, theme);
        } catch {
          // ignore
        }
      } catch {
        // If status can't be fetched, do nothing; pages will surface API errors.
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [pathname]);

  return null;
}
