"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useApp } from "./Providers";
import { LANGS } from "@/lib/i18n";
import { User, getUser, setUser } from "@/lib/api";

export function Logo({ size = 20, light = false }: { size?: number; light?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2">
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" aria-hidden>
        <rect x="1.5" y="1.5" width="21" height="21" rx="5.5" stroke={light ? "#7fc1a3" : "var(--accent)"} strokeWidth="1.6" />
        <path d="M7 12h6.2M13.2 12l-2.3-2.4M13.2 12l-2.3 2.4" stroke="var(--accent)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        <circle cx="16.8" cy="12" r="2.2" fill="var(--accent)" />
      </svg>
      <span className={`serif text-[18px] tracking-tight ${light ? "text-[#ecebe3]" : "text-ink"}`}>CreditGateway</span>
    </span>
  );
}

export function useAuth(): User | null {
  const router = useRouter();
  const [u, setU] = useState<User | null>(null);
  useEffect(() => {
    const x = getUser();
    if (!x) router.replace("/login");
    else setU(x);
  }, [router]);
  return u;
}

export function Shell({ children, wide = false }: { children: React.ReactNode; wide?: boolean }) {
  const { t, lang, setLang, theme, toggleTheme } = useApp();
  const path = usePathname();
  const router = useRouter();
  const user = useAuth();
  const nav = [
    { href: "/", label: t("nav.queue") },
    { href: "/portfolio", label: t("nav.portfolio") },
    { href: "/system", label: t("nav.system") },
    { href: "/verify", label: t("nav.verify") },
  ];
  if (!user) return <div className="min-h-screen" />;
  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-30 border-b border-line bg-bg/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-[1400px] items-center gap-6 px-4 sm:px-6">
          <Link href="/" aria-label="CreditGateway home"><Logo /></Link>
          <nav className="hidden md:flex items-center gap-1">
            {nav.map((n) => {
              const on = n.href === "/" ? path === "/" || path.startsWith("/cases") : path.startsWith(n.href);
              return (
                <Link key={n.href} href={n.href} className={`rounded-md px-3 py-1.5 text-[13px] transition ${on ? "bg-surface-2 text-ink font-medium" : "text-muted hover:text-ink"}`}>
                  {n.label}
                </Link>
              );
            })}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <div className="flex rounded-md border border-line overflow-hidden" role="group" aria-label="language">
              {LANGS.map((l) => (
                <button key={l.code} onClick={() => setLang(l.code)} aria-pressed={lang === l.code}
                  className={`px-2 py-1 text-[11px] font-medium ${lang === l.code ? "bg-ink text-bg" : "text-muted hover:text-ink"}`}>{l.label}</button>
              ))}
            </div>
            <button onClick={toggleTheme} className="rounded-md border border-line px-2 py-1 text-[11px] text-muted hover:text-ink" aria-label="toggle theme">
              {theme === "dark" ? "☀" : "☾"}
            </button>
            <div className="hidden sm:block text-right leading-tight">
              <div className="text-[12px] text-ink">{user.name}</div>
              <div className="text-[10.5px] text-muted">{user.role}</div>
            </div>
            <button onClick={() => { setUser(null); router.replace("/login"); }} className="text-[12px] text-muted hover:text-ink">{t("nav.signout")}</button>
          </div>
        </div>
        <nav className="md:hidden flex gap-1 overflow-x-auto px-4 pb-2 scroll-thin">
          {nav.map((n) => (
            <Link key={n.href} href={n.href} className={`whitespace-nowrap rounded-md px-3 py-1 text-[12.5px] ${path === n.href ? "bg-surface-2 text-ink" : "text-muted"}`}>{n.label}</Link>
          ))}
        </nav>
      </header>
      <main className={`mx-auto w-full flex-1 px-4 py-6 sm:px-6 ${wide ? "max-w-[1560px]" : "max-w-[1400px]"}`}>{children}</main>
      <footer className="border-t border-line px-4 py-4 text-center text-[11.5px] text-muted">{t("ft.disclaimer")}</footer>
    </div>
  );
}
