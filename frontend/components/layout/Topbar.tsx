"use client";

import { LogOut, Menu, UserCircle } from "lucide-react";
import { useRouter, usePathname } from "next/navigation";
import { useState } from "react";
import { NAV_ITEMS } from "./Sidebar";

function currentSectionLabel(pathname: string): string {
  const match = [...NAV_ITEMS]
    .sort((a, b) => b.href.length - a.href.length)
    .find((item) => (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)));
  return match?.label ?? "";
}

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const pathname = usePathname();
  const router = useRouter();
  const label = currentSectionLabel(pathname);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  async function handleLogout() {
    setIsLoggingOut(true);
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
      router.refresh();
    }
  }

  return (
    <header className="sticky top-0 z-20 flex h-16 shrink-0 items-center gap-3 border-b border-border bg-surface-card/95 px-4 backdrop-blur sm:px-6">
      <button
        type="button"
        onClick={onMenuClick}
        className="rounded-md p-2 text-text-secondary hover:bg-surface lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-5 w-5" />
      </button>

      <div className="min-w-0 flex-1">
        <span className="truncate text-sm font-medium text-text-secondary">
          {label}
        </span>
      </div>

      <div className="flex shrink-0 items-center gap-3 text-sm text-text-secondary">
        <span className="hidden items-center gap-2 sm:flex">
          <UserCircle className="h-6 w-6" />
          Administrator
        </span>
        <button
          type="button"
          onClick={handleLogout}
          disabled={isLoggingOut}
          className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-text-secondary hover:bg-surface hover:text-text-primary disabled:opacity-50"
        >
          <LogOut className="h-4 w-4" />
          <span className="hidden sm:inline">Logout</span>
        </button>
      </div>
    </header>
  );
}
