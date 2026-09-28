"use client";

import { ReactNode } from "react";

/**
 * A minimal, reusable modal for confirmation flows — deliberately not a
 * new dependency (no dialog/modal library added); it reuses the same
 * fixed-overlay pattern the Sidebar's own mobile drawer already uses.
 * The caller owns everything inside (message, inputs, buttons); this
 * component only owns the overlay/positioning/focus container.
 */
export function ConfirmDialog({
  open,
  title,
  onClose,
  children,
}: {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="fixed inset-0 bg-black/40" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        className="relative z-10 w-full max-w-md rounded-lg border border-border bg-surface-card p-5 shadow-lg"
      >
        <h2 id="confirm-dialog-title" className="text-base font-semibold text-text-primary">
          {title}
        </h2>
        <div className="mt-3 flex flex-col gap-3 text-sm text-text-secondary">{children}</div>
      </div>
    </div>
  );
}
