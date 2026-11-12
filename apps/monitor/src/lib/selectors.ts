import type { Job, MonitorSnapshot, ProductionEvent } from "@/types/monitor";

export type EventFilter = "all" | "tasks" | "voices" | "decisions" | "issues";
export function filterEvents(
  events: ProductionEvent[],
  filter: EventFilter,
  query = "",
  oldestFirst = false,
) {
  const needle = query.trim().toLowerCase();
  return events
    .filter((event) => {
      const category =
        filter === "all" ||
        (filter === "tasks" &&
          !["voice_change", "decision", "intake", "delivery"].includes(
            event.kind,
          )) ||
        (filter === "voices" && event.kind === "voice_change") ||
        (filter === "decisions" &&
          ["decision", "delivery"].includes(event.kind)) ||
        (filter === "issues" &&
          ["failed", "interrupted", "stale"].includes(event.kind));
      return (
        category &&
        (!needle ||
          [event.message, event.label, event.detail, event.part].some((value) =>
            value?.toLowerCase().includes(needle),
          ))
      );
    })
    .sort(
      (a, b) => (Date.parse(a.at) - Date.parse(b.at)) * (oldestFirst ? 1 : -1),
    );
}

export function taskDuration(events: ProductionEvent[]) {
  return events.reduce(
    (sum, event) =>
      sum +
      (event.kind !== "cached" && Number.isFinite(event.duration_seconds)
        ? event.duration_seconds || 0
        : 0),
    0,
  );
}

const stageOrder = [
  "voice_setup",
  "audition",
  "narration",
  "alignment",
  "timeline",
  "images",
  "sound",
  "mix",
  "subtitles",
  "render",
  "qa",
];
export function orderedJobs(jobs: Job[]) {
  return jobs
    .filter((job) => !job.id?.startsWith("run:"))
    .toSorted((a, b) => {
      const rank = (job: Job) => {
        const index = stageOrder.indexOf(job.id?.split(":")[0] || "");
        return index === -1 ? stageOrder.length : index;
      };
      return (
        (a.part || "").localeCompare(b.part || "") ||
        rank(a) - rank(b) ||
        Number(a.id?.endsWith(":final")) - Number(b.id?.endsWith(":final")) ||
        (a.id || "").localeCompare(b.id || "")
      );
    });
}

export function operationPercent(snapshot: MonitorSnapshot): number | null {
  const percent = snapshot.current.percent;
  return typeof percent === "number" && Number.isFinite(percent)
    ? Math.min(100, Math.max(0, percent))
    : null;
}
