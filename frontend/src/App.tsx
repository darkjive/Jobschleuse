import { useEffect, useRef } from "react";
import { UserRound } from "lucide-react";
import { Link, Outlet } from "react-router";
import { CommandPalette } from "@/components/command-palette";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { HeaderActionsOutlet, HeaderActionsProvider } from "@/lib/header-actions";

function Header() {
  // Designsystem-Soundschalter (/ds/sounds.js) in die Header-Aktionen einhängen
  const soundRef = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    const host = soundRef.current;
    if (host) window.dsSound?.mountToggle(host);
    return () => host?.replaceChildren();
  }, []);

  return (
    <>
      <header className="ds-header">
        <div className="ds-brand">
          <img src="/favicon.svg" width={28} height={28} alt="" />
          <h1>Jobschleuse</h1>
          <span className="ds-muted ds-hide-mobile text-sm font-normal">Stellen rein, Bewerbungen raus.</span>
        </div>
        <div className="ds-header-actions">
          <span ref={soundRef} className="contents" />
          <Button variant="outline" size="icon" asChild>
            <Link to="/profil" aria-label="Profil" title="Profil">
              <UserRound />
            </Link>
          </Button>
          <ThemeToggle />
        </div>
      </header>
      <HeaderActionsOutlet className="flex flex-wrap items-center gap-2 border-b border-border bg-card px-[var(--page-inset)] py-[var(--space-2)] empty:hidden" />
    </>
  );
}

export function Layout() {
  return (
    <HeaderActionsProvider>
      <div className="flex h-svh flex-col">
        <Header />
        <main className="mx-auto w-full max-w-[var(--content-max)] flex-1 overflow-hidden p-[var(--page-pad)]">
          <Outlet />
        </main>
        <CommandPalette />
      </div>
    </HeaderActionsProvider>
  );
}
