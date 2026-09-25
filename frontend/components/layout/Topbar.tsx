"use client";

import { Menu, UserCircle } from "lucide-react";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "./Sidebar";

function currentSectionLabel(pathname: string): string {
  const match = [...NAV_ITEMS]
    .sort((a, b) => b.href.length - a.href.length)
    .find((item) => (item.href === "/" ? pathname === "/" : pathname.startsWith(item.href)));
  return match?.label ?? "";
}

export function Topbar({ onMenuClick }: { onMenuClick: () => void }) {
  const pathname = usePathname();
  const label = currentSectionLabel(pathname);

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

      <div className="flex shrink-0 items-center gap-2 text-sm text-text-secondary">
        <UserCircle className="h-6 w-6" />
        <span className="hidden sm:inline">Administrator</span>
      </div>
    </header>
  );
}
