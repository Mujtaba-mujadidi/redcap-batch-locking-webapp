import { formatStatus, statusTone } from "@/lib/format";
import type { JobStatus } from "@/lib/types";

type StatusPillProps = {
  status: JobStatus;
};

export function StatusPill({ status }: StatusPillProps) {
  const toneClass =
    statusTone(status) === "good"
      ? "status-active"
      : statusTone(status) === "warn"
        ? "status-review"
        : "status-inactive";
  return (
    <span className={`status-pill ${toneClass}`}>
      {formatStatus(status)}
    </span>
  );
}
