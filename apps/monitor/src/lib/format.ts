export function duration(
  value: number | null | undefined,
  precise = false,
): string {
  if (value == null || !Number.isFinite(value)) return "Not recorded";
  if (value < 1)
    return precise ? `${Math.round(Math.max(0, value) * 1000)} ms` : "<1 sec";
  const seconds = Math.max(0, Math.round(value));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  const remainder = seconds % 60;
  return hours
    ? `${hours}h ${minutes}m`
    : minutes
      ? `${minutes}m ${remainder}s`
      : `${seconds} sec`;
}

export function timecode(value: number | null | undefined): string {
  const seconds = Math.max(0, Math.floor(value || 0));
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${hours ? String(hours).padStart(2, "0") + ":" : ""}${String(minutes).padStart(2, "0")}:${String(seconds % 60).padStart(2, "0")}`;
}

export function timestamp(
  value: string | number | null | undefined,
  includeDate = false,
): string {
  if (value == null) return "Not recorded";
  const date = new Date(typeof value === "number" ? value * 1000 : value);
  if (!Number.isFinite(date.getTime())) return "Not recorded";
  return new Intl.DateTimeFormat(undefined, {
    ...(includeDate ? ({ month: "short", day: "numeric" } as const) : {}),
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

export function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isFinite(date.getTime())
    ? new Intl.DateTimeFormat(undefined, {
        weekday: "long",
        month: "long",
        day: "numeric",
      }).format(date)
    : "Time not recorded";
}

export function relative(
  value: string | null | undefined,
  now = Date.now(),
): string {
  if (!value) return "No timestamp";
  const seconds = Math.max(0, (now - Date.parse(value)) / 1000);
  if (!Number.isFinite(seconds)) return "No timestamp";
  return seconds < 10 ? "Just now" : `${duration(seconds)} ago`;
}

export function partLabel(id: string): string {
  return `Part ${Number(id.replace("part_", "")) || id}`;
}

export const stateLabels: Record<string, string> = {
  running: "In progress",
  complete: "Completed",
  cached: "Reused",
  pending: "Queued",
  failed: "Failed",
  interrupted: "Interrupted",
  stale: "Signal lost",
  reported: "Reported",
  waiting: "Waiting",
  provider_wait: "Awaiting provider",
  idle: "No active task",
};
