import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Stock Insights",
  description: "US equities (NYSE/NASDAQ) insights -- personal MVP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="min-h-screen flex flex-col">
          <header className="border-b border-neutral-800">
            <div className="max-w-6xl mx-auto px-4 py-3 flex items-center gap-6">
              <Link href="/" className="font-semibold tracking-tight">
                Stock Insights
              </Link>
              <nav className="flex gap-4 text-sm text-neutral-400">
                <Link href="/" className="hover:text-neutral-100">
                  Dashboard
                </Link>
                <Link href="/search" className="hover:text-neutral-100">
                  Search
                </Link>
                <Link href="/tickers" className="hover:text-neutral-100">
                  All Tickers
                </Link>
                <Link href="/momentum" className="hover:text-neutral-100">
                  Momentum
                </Link>
              </nav>
            </div>
          </header>
          <main className="flex-1 max-w-6xl w-full mx-auto px-4 py-6">{children}</main>
          <footer className="border-t border-neutral-800 text-xs text-neutral-500">
            <div className="max-w-6xl mx-auto px-4 py-3">
              Data via Yahoo Finance / Stooq (free, unofficial). Not investment advice.
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
