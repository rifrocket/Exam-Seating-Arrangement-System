"use client";

import { AlertTriangle, ShieldAlert } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Button } from "@/components/ui/Button";
import { Card, CardHeader } from "@/components/ui/Card";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { PageHeader } from "@/components/ui/PageHeader";
import { resetDatabase } from "@/lib/api";

type DialogPhase = "confirm" | "password";

export default function SettingsPage() {
  const router = useRouter();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [phase, setPhase] = useState<DialogPhase>("confirm");
  const [password, setPassword] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [succeeded, setSucceeded] = useState(false);

  function openDialog() {
    setPhase("confirm");
    setPassword("");
    setError(null);
    setSucceeded(false);
    setDialogOpen(true);
  }

  function closeDialog() {
    if (isSubmitting) return; // never interrupt an in-flight reset
    setDialogOpen(false);
    setPassword("");
    setError(null);
  }

  async function handleReset() {
    setIsSubmitting(true);
    setError(null);
    try {
      await resetDatabase(password);
      setPassword("");
      setSucceeded(true);
      // Give the administrator a moment to see the success message, then
      // leave this page — the rest of the app now has nothing in it, so
      // there is no stale data anywhere to worry about once we're on a
      // fresh page load of the dashboard.
      setTimeout(() => {
        setDialogOpen(false);
        router.push("/");
        router.refresh();
      }, 1200);
    } catch (err) {
      setPassword("");
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Settings"
        description="Administrative actions for this application"
      />

      <Card className="border-danger-bg">
        <CardHeader
          title="Danger Zone"
          description="Irreversible, application-wide actions."
        />
        <div className="flex flex-col gap-4 p-5">
          <div className="flex items-start gap-3 rounded-md border border-danger-bg bg-danger-bg/40 p-4">
            <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-danger-text" />
            <div className="text-sm text-danger-text">
              <p className="font-medium">Reset Database</p>
              <p className="mt-1">
                Permanently deletes all registered students, courses, exams,
                rooms, schedules, seating generations, examination sessions,
                and other application data. This cannot be undone.
              </p>
            </div>
          </div>
          <div>
            <Button
              variant="danger"
              onClick={openDialog}
              icon={<ShieldAlert className="h-4 w-4" />}
            >
              Reset Database
            </Button>
          </div>
        </div>
      </Card>

      <ConfirmDialog
        open={dialogOpen}
        title={phase === "confirm" ? "Reset Database?" : "Confirm Administrator Password"}
        onClose={closeDialog}
      >
        {phase === "confirm" && (
          <>
            <p>
              This will permanently delete all registered students, courses,
              exams, rooms, schedules, seating generations, examination
              sessions, and other application data. The database schema
              itself is preserved, but every record in it will be gone.
            </p>
            <p className="font-medium text-text-primary">
              This action cannot be undone.
            </p>
            <div className="mt-2 flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={closeDialog}>
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={() => setPhase("password")}
              >
                Continue
              </Button>
            </div>
          </>
        )}

        {phase === "password" && !succeeded && (
          <>
            <p>Enter the administrator password to permanently reset the database.</p>
            <label className="flex flex-col gap-1 text-xs font-medium text-text-secondary">
              Administrator password
              <input
                type="password"
                autoComplete="off"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={isSubmitting}
                className="rounded-md border border-border bg-white px-3 py-2 text-sm text-text-primary focus:border-brand-500 focus:outline-none disabled:opacity-50"
                placeholder="Administrator password"
              />
            </label>
            {error && (
              <p role="alert" className="text-sm text-danger-text">
                {error}
              </p>
            )}
            <div className="mt-2 flex justify-end gap-2">
              <Button
                variant="secondary"
                size="sm"
                onClick={closeDialog}
                disabled={isSubmitting}
              >
                Cancel
              </Button>
              <Button
                variant="danger"
                size="sm"
                onClick={handleReset}
                loading={isSubmitting}
                disabled={!password || isSubmitting}
              >
                Reset Database
              </Button>
            </div>
          </>
        )}

        {succeeded && (
          <p className="text-sm font-medium text-success-text">
            Database reset successfully. Redirecting…
          </p>
        )}
      </ConfirmDialog>
    </div>
  );
}
