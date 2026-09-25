import { ReactNode } from "react";

export function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div
      className={`rounded-lg border border-border bg-surface-card shadow-sm ${className}`}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
      <div>
        <h2 className="text-sm font-semibold text-text-primary">{title}</h2>
        {description && (
          <p className="mt-0.5 text-xs text-text-secondary">{description}</p>
        )}
      </div>
      {action}
    </div>
  );
}

export function StatCard({
  label,
  value,
  icon,
  tone = "brand",
}: {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  tone?: "brand" | "success" | "warning" | "danger" | "neutral";
}) {
  const toneClasses: Record<string, string> = {
    brand: "bg-brand-50 text-brand-600",
    success: "bg-success-bg text-success-text",
    warning: "bg-warning-bg text-warning-text",
    danger: "bg-danger-bg text-danger-text",
    neutral: "bg-neutral-bg text-neutral-text",
  };

  return (
    <Card className="flex items-center gap-4 p-4">
      {icon && (
        <div
          className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-lg ${toneClasses[tone]}`}
        >
          {icon}
        </div>
      )}
      <div className="min-w-0">
        <div className="truncate text-xs font-medium text-text-secondary">
          {label}
        </div>
        <div className="text-2xl font-semibold text-text-primary">
          {value}
        </div>
      </div>
    </Card>
  );
}
