import type { CastChange, MonitorSnapshot, Project } from "@/types/monitor";

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal, cache: "no-store" });
  if (!response.ok) throw new Error(`The monitor returned ${response.status}`);
  return response.json() as Promise<T>;
}

export async function fetchProjects(signal: AbortSignal): Promise<Project[]> {
  const value = await get<{ projects: Project[] }>("/api/projects", signal);
  if (!Array.isArray(value.projects))
    throw new Error("Project records are unavailable");
  return value.projects;
}

export async function fetchSnapshot(
  project: string,
  signal: AbortSignal,
): Promise<MonitorSnapshot> {
  const value = await get<MonitorSnapshot>(
    `/api/status?project=${encodeURIComponent(project)}`,
    signal,
  );
  if (
    value.project?.id !== project ||
    !value.current ||
    !Array.isArray(value.media) ||
    !Array.isArray(value.events)
  ) {
    throw new Error("Production records are being updated");
  }
  return value;
}

export async function requestCastChange(
  token: string,
  body: {
    project: string;
    character_id: string;
    request: string;
    base_version: string;
    id: string;
  },
): Promise<CastChange> {
  const response = await fetch("/api/cast-change", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Studio-Cast-Token": token,
    },
    body: JSON.stringify(body),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      result.error || "The character change could not be recorded",
    );
  return result as CastChange;
}
