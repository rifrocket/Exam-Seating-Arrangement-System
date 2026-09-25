import { AlertTriangle } from "lucide-react";
import { SeatingGenerationResult } from "@/lib/api";

/**
 * Renders the two distinct shortage reasons a generation can have
 * (scheduled_allocation_shortage vs. physical_capacity_shortage) as
 * separate, clearly-labeled items — never collapsed into one generic
 * "capacity shortage" message, since they mean different things and call
 * for different fixes.
 */
export function CapacityDiagnostics({
  result,
}: {
  result: SeatingGenerationResult;
}) {
  if (!result.capacity_shortage) return null;

  return (
    <div className="rounded-lg border border-danger-bg bg-danger-bg/50 p-4">
      <p className="mb-2 flex items-center gap-2 text-sm font-medium text-danger-text">
        <AlertTriangle className="h-4 w-4" />
        {result.total_unassigned} student(s) could not be seated
      </p>
      <ul className="flex flex-col gap-2 text-xs text-danger-text">
        {result.scheduled_allocation_shortage && (
          <li className="rounded-md bg-white/60 p-2">
            <span className="font-semibold">Scheduled allocation shortage</span>{" "}
            — {result.total_registered} registered vs. only{" "}
            {result.scheduled_student_count} seat(s) scheduled across this
            exam&apos;s rooms. The rooms may have had physical room to spare;
            the schedule simply didn&apos;t allocate enough.
          </li>
        )}
        {result.physical_capacity_shortage && (
          <li className="rounded-md bg-white/60 p-2">
            <span className="font-semibold">Physical capacity shortage</span> —
            the rooms assigned to this exam have only{" "}
            {result.total_physical_capacity} physical seat(s) total,
            regardless of what was scheduled.
          </li>
        )}
      </ul>
    </div>
  );
}
