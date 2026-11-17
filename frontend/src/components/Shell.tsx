"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { clock } from "@/lib/format";

const LINKS = [
  { href: "/", label: "Dashboard" },
  { href: "/backtest", label: "Backtest" },
  { href: "/history", label: "History" },
  { href: "/alerts", label: "Alerts" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [now, setNow] = useState("—");

  useEffect(() => {
    const tick = () => setNow(clock(new Date()));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);

  return (
    <div className="mx-auto min-h-screen max-w-[1440px] px-4 pb-16 pt-4 sm:px-6">
      <div className="mb-4 flex flex-wrap items-center gap-x-6 gap-y-3">
        <Link href="/" className="leading-none">
          <div className="font-display text-2xl tracking-tight">TrendLens</div>
          <div className="mt-1 text-[11px] uppercase tracking-[0.18em] text-muted">EUR/USD decision support</div>
        </Link>
        <nav className="flex flex-1 gap-1 overflow-x-auto">
          {LINKS.map((link) => {
            const on = pathname === link.href;
            return (
              <Link
                key={link.href}
                href={link.href}
                className={`rounded-full px-3 py-1.5 text-sm ${on ? "bg-white/10 text-ink" : "text-muted hover:text-ink"}`}
              >
                {link.label}
              </Link>
            );
          })}
        </nav>
        <div className="font-mono text-xs text-muted">{now}</div>
      </div>
      {children}
      <p className="mt-8 text-center text-xs text-muted">
        Decision support only. TrendLens does not place trades. For educational purposes only, not financial advice.
      </p>
    </div>
  );
}
