import { Outlet } from "react-router";
import { CommandPalette } from "@/components/command-palette";
import { ThemeToggle } from "@/components/theme-toggle";
import { HeaderActionsOutlet, HeaderActionsProvider } from "@/lib/header-actions";

function Header() {
  return (
    <header className="flex flex-col gap-4 border-b border-border px-6 py-4">
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" aria-hidden="true">
            <path d="M3 4h18l-7 8v7l-4 2v-9L3 4z" className="fill-primary" />
          </svg>
          <div>
            <h1 className="text-lg leading-tight font-semibold">Jobschleuse</h1>
            <p className="text-sm text-muted-foreground">Stellen rein, Bewerbungen raus.</p>
          </div>
        </div>
        <ThemeToggle />
      </div>
      <HeaderActionsOutlet className="flex flex-wrap items-center gap-2" />
    </header>
  );
}

export function Layout() {
  return (
    <HeaderActionsProvider>
      <div className="mx-auto flex min-h-svh max-w-6xl flex-col">
        <Header />
        <main className="flex-1 overflow-hidden p-6">
          <Outlet />
        </main>
        <footer className="border-t border-border px-6 py-4 text-center text-sm text-muted-foreground">
          <a
            href="https://paypal.me/AlainRitter"
            target="_blank"
            rel="noopener noreferrer"
            className="hover:text-foreground"
          >
            Unterstützen via PayPal
          </a>
        </footer>
        <CommandPalette />
      </div>
    </HeaderActionsProvider>
  );
}
