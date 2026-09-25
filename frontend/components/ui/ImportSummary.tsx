import { AlertCircle, AlertTriangle, GitMerge } from "lucide-react";
import { ReactNode } from "react";
import { ConflictOut, ValidationErrorOut, WarningOut } from "@/lib/api";
import { StatusBadge } from "./Badge";

export function ImportStat({
  label,
  value,
}: {
  label: string;
  value: number;
}) {
  return (
    <div className="rounded-md border border-border bg-surface px-3 py-2">
      <div className="text-lg font-semibold text-text-primary">{value}</div>
      <div className="text-xs text-text-secondary">{label}</div>
    </div>
  );
}

function IssueList({
  icon,
  heading,
  items,
}: {
  icon: ReactNode;
  heading: string;
  items: ReactNode[];
}) {
  if (items.length === 0) return null;
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-text-secondary">
        {icon}
        {heading} ({items.length})
      </div>
      <ul className="flex flex-col gap-1">
        {items.map((item, index) => (
          <li
            key={index}
            className="rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-text-secondary"
          >
            {item}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function ImportSummary({
  status,
  stats,
  validationErrors = [],
  conflicts = [],
  warnings = [],
}: {
  status: "success" | "partial" | "failed";
  stats: { label: string; value: number }[];
  validationErrors?: ValidationErrorOut[];
  conflicts?: ConflictOut[];
  warnings?: WarningOut[];
}) {
  return (
    <div className="flex flex-col gap-4 rounded-lg border border-border bg-surface-card p-4">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-text-secondary">
          Import status:
        </span>
        <StatusBadge status={status} />
      </div>

      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
        {stats.map((stat) => (
          <ImportStat key={stat.label} label={stat.label} value={stat.value} />
        ))}
      </div>

      <IssueList
        icon={<AlertCircle className="h-3.5 w-3.5" />}
        heading="Validation errors"
        items={validationErrors.map((issue, index) => (
          <span key={index}>
            {issue.line_number != null ? `Line ${issue.line_number}: ` : ""}
            {issue.field ? `[${issue.field}] ` : ""}
            {issue.message}
          </span>
        ))}
      />

      <IssueList
        icon={<GitMerge className="h-3.5 w-3.5" />}
        heading="Conflicts"
        items={conflicts.map((conflict, index) => (
          <span key={index}>
            Line {conflict.line_number}: {conflict.kind} for &quot;
            {conflict.key}&quot; — stored &quot;{conflict.existing_value}&quot;
            vs incoming &quot;{conflict.incoming_value}&quot;
          </span>
        ))}
      />

      <IssueList
        icon={<AlertTriangle className="h-3.5 w-3.5" />}
        heading="Warnings"
        items={warnings.map((warning, index) => (
          <span key={index}>
            {warning.line_number != null ? `Line ${warning.line_number}: ` : ""}
            {warning.message}
          </span>
        ))}
      />
    </div>
  );
}
