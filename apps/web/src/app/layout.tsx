import type { Metadata, Viewport } from "next";

import "./globals.css";

export const metadata: Metadata = {
  title: "MARK LIV",
  description: "A professional AI platform: chat, voice, and a connected desktop companion.",
};

export const viewport: Viewport = {
  themeColor: "#04070d",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
