import { ReactNode } from "react";

type Tone = "success" | "warning" | "danger" | "neutral" | "brand";

const tones: Record<Tone, string> = {
  success: "bg-success-bg text-success-text",
  warning: "bg-warning-bg text-warning-text",
  danger: "bg-danger-bg text-danger-text",
  neutral: "bg-neutral-bg text-neutral-text",
  brand: "bg-brand-100 text-brand-700",
};

export function Badge({
  tone = "neutral",
  children,
}: {
  tone?: Tone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  );
}

type GenerationStatus = "pending" | "success" | "partial" | "failed";
type ImportStatus = "success" | "partial" | "failed";

const STATUS_TONE: Record<GenerationStatus, Tone> = {
  pending: "neutral",
  success: "success",
  partial: "warning",
  failed: "danger",
};

const STATUS_LABEL: Record<GenerationStatus, string> = {
  pending: "Pending",
  success: "Success",
  partial: "Partial",
  failed: "Failed",
};

export function StatusBadge({
  status,
}: {
  status: GenerationStatus | ImportStatus;
}) {
  return <Badge tone={STATUS_TONE[status]}>{STATUS_LABEL[status]}</Badge>;
}

export function SeatingStatusBadge({
  hasGeneration,
  status,
}: {
  hasGeneration: boolean;
  status?: GenerationStatus;
}) {
  if (!hasGeneration || !status) {
    return <Badge tone="neutral">Not Generated</Badge>;
  }
  return <StatusBadge status={status} />;
}
