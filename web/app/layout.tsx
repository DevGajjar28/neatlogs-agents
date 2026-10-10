import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { AppShell } from "@/components/shell/AppShell";
import { QueryProvider } from "@/components/providers/query-provider";
import { Toaster } from "@/components/ui/sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "SignalSDR",
  description: "Outbound agent control plane for neatHack",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="min-h-screen antialiased">
        <QueryProvider>
          <AppShell>{children}</AppShell>
          <Toaster position="bottom-right" richColors closeButton visibleToasts={1} />
        </QueryProvider>
      </body>
    </html>
  );
}
