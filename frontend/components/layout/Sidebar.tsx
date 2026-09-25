"use client";

import {
  BookOpen,
  Building2,
  CalendarClock,
  ClipboardList,
  FileBarChart,
  GraduationCap,
  LayoutDashboard,
  ListChecks,
  Users,
  X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/registrations", label: "Registrations", icon: ClipboardList },
  { href: "/students", label: "Students", icon: Users },
  { href: "/courses", label: "Courses", icon: BookOpen },
  { href: "/exams", label: "Exams", icon: ListChecks },
  { href: "/schedule", label: "Schedule", icon: CalendarClock },
  { href: "/rooms", label: "Rooms", icon: Building2 },
  { href: "/seating-generations", label: "Seating Generations", icon: GraduationCap },
  { href: "/reports", label: "Reports", icon: FileBarChart },
];

function isActive(pathname: string, href: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({
  mobileOpen,
  onClose,
}: {
  mobileOpen: boolean;
  onClose: () => void;
}) {
  const pathname = usePathname();

  const content = (
    <div className="flex h-full flex-col bg-sidebar text-sidebar-text">
      <div className="flex h-16 shrink-0 items-center gap-2 border-b border-sidebar-border px-5">
        <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-600 text-white">
          <GraduationCap className="h-4.5 w-4.5" />
        </div>
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">
            Exam Seating
          </div>
          <div className="truncate text-[11px] text-sidebar-text">
            Arrangement System
          </div>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded-md p-1 text-sidebar-text hover:bg-sidebar-hover lg:hidden"
          aria-label="Close navigation"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <nav className="flex-1 space-y-0.5 overflow-y-auto px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const active = isActive(pathname, item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
              onClick={onClose}
              className={`flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
                active
                  ? "bg-sidebar-active text-sidebar-text-active"
                  : "text-sidebar-text hover:bg-sidebar-hover hover:text-sidebar-text-active"
              }`}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="truncate">{item.label}</span>
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-sidebar-border px-5 py-3 text-[11px] text-sidebar-text">
        Sequential seating engine
      </div>
    </div>
  );

  return (
    <>
      {/* Desktop: fixed sidebar */}
      <aside className="hidden lg:fixed lg:inset-y-0 lg:left-0 lg:z-30 lg:block lg:w-64">
        {content}
      </aside>

      {/* Mobile: slide-over drawer */}
      {mobileOpen && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="fixed inset-0 bg-black/40"
            onClick={onClose}
            aria-hidden
          />
          <aside className="fixed inset-y-0 left-0 z-50 w-64">{content}</aside>
        </div>
      )}
    </>
  );
}

export { NAV_ITEMS };
