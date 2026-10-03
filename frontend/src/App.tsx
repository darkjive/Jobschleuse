import { UserRound } from "lucide-react";
import { Link, Outlet } from "react-router";
import { CommandPalette } from "@/components/command-palette";
import { Button } from "@/components/ui/button";
import { ThemeToggle } from "@/components/theme-toggle";
import { HeaderActionsOutlet, HeaderActionsProvider } from "@/lib/header-actions";

function Header() {
  return (
    <header className="border-b border-border bg-card">
      <div className="ds-header justify-between border-b-0 bg-transparent">
        <div className="ds-brand">
          <img src="/favicon.svg" width={28} height={28} alt="" />
          <h1>Jobschleuse</h1>
          <span className="ds-muted ds-hide-mobile text-sm font-normal">Stellen rein, Bewerbungen raus.</span>
        </div>
        <div className="ds-header-actions">
          <Button variant="outline" size="icon" asChild>
            <Link to="/profil" aria-label="Profil" title="Profil">
              <UserRound />
            </Link>
          </Button>
          <ThemeToggle />
        </div>
      </div>
      <HeaderActionsOutlet className="flex flex-wrap items-center gap-2 px-[var(--page-inset)] pb-[var(--space-3)] empty:hidden" />
    </header>
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
