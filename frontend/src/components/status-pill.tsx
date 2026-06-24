import { formatStatus, statusTone } from "@/lib/format";
import type { JobStatus } from "@/lib/types";

type StatusPillProps = {
  label?: string;
  status: JobStatus;
  toneClassName?: string;
};

export function StatusPill({ label, status, toneClassName }: StatusPillProps) {
  const toneClass =
    toneClassName ||
    (statusTone(status) === "good"
      ? "status-active"
      : statusTone(status) === "warn"
        ? "status-review"
        : "status-inactive");
  return (
    <span className={`status-pill ${toneClass}`}>
      {label || formatStatus(status)}
    </span>
  );
}
