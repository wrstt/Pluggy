import type { Metadata } from "next";
import "./globals.css";
import "@/styles/tokens.css";
import "@/styles/themes/presets.css";
import { AppShell } from "@/components/shell/AppShell";
import { ProfileEnforcerClient } from "@/components/auth/ProfileEnforcerClient";
import { DEFAULT_THEME_ID } from "@/lib/theme/presets";

export const metadata: Metadata = {
  title: "Pluggy",
  description: "Software-first discovery and transfer workspace",
  icons: {
    icon: "/favicon.ico",
    apple: "/brand/pluggy-mark.png",
    shortcut: "/favicon-32x32.png"
  }
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <head />
      <body>
        <ProfileEnforcerClient />
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
