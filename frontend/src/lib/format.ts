import type { JobStatus, Role } from "@/lib/types";

export function formatDate(value: string | null): string {
  if (!value) {
    return "Not available";
  }

  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatRole(role: Role): string {
  return role.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase());
}

export function formatStatus(status: string): string {
  return status.replaceAll("_", " ").replace(/\b\w/g, (value) => value.toUpperCase());
}

export function statusTone(status: JobStatus): "good" | "warn" | "muted" {
  if (status === "completed") {
    return "good";
  }
  if (
    status === "awaiting_mapping_confirmation" ||
    status === "ready" ||
    status === "queued" ||
    status === "running" ||
    status === "waiting_due_to_rate_limit" ||
    status === "cancel_requested"
  ) {
    return "warn";
  }
  return "muted";
}
