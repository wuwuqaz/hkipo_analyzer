"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const nav = [
  { href: "/", label: "Dashboard" },
  { href: "/upload", label: "Upload" },
  { href: "/history", label: "History" },
  { href: "/peers", label: "Peers" },
  { href: "/reanalyze", label: "Reanalyze" },
  { href: "/backtest", label: "回测" },
];

export function Navbar() {
  const pathname = usePathname();

  return (
    <nav className="overflow-x-hidden border-b border-[var(--border)] bg-[var(--surface-strong)]/80 backdrop-blur">
      <div className="mx-auto flex max-w-6xl items-center gap-6 px-6 py-4 sm:px-10 lg:px-12">
        <Link href="/" className="text-lg font-semibold tracking-tight text-white">
          HK IPO Analyzer
        </Link>
        <div className="ml-auto flex items-center gap-1">
          {nav.map((item) => {
            const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`rounded-full px-4 py-1.5 text-sm font-medium transition ${
                  active
                    ? "bg-white/10 text-[var(--accent)]"
                    : "text-[var(--muted)] hover:text-[var(--foreground)]"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    </nav>
  );
}
