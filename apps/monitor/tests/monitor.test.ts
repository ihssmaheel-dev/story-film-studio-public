import { afterEach, describe, expect, it, vi } from "vitest";
import { duration, timecode } from "../src/lib/format";
import {
  filterEvents,
  isProjectDelivered,
  operationPercent,
  orderedJobs,
  taskDuration,
} from "../src/lib/selectors";
import { fetchProjects, fetchSnapshot } from "../src/lib/api";
import type {
  Job,
  MonitorSnapshot,
  ProductionEvent,
} from "../src/types/monitor";

function event(
  id: string,
  at: string,
  kind: string,
  seconds?: number,
): ProductionEvent {
  return {
    id,
    at,
    kind,
    job: "render:part_001:preview",
    label: "Rendering",
    message: id,
    duration_seconds: seconds,
  };
}

describe("actual clocks and chronology", () => {
  it("distinguishes missing duration from measured zero", () => {
    expect(duration(null, true)).toBe("Not recorded");
    expect(duration(0, true)).toBe("0 ms");
    expect(duration(0.082, true)).toBe("82 ms");
  });
  it("supports full films beyond one hour", () => {
    expect(timecode(3662)).toBe("01:01:02");
    expect(timecode(44.261958)).toBe("00:44");
  });
  it("sorts real instants across timezone offsets", () => {
    const values = [
      event("earlier", "2026-10-30T12:30:00+05:30", "complete"),
      event("later", "2026-10-30T07:01:00Z", "decision"),
    ];
    expect(filterEvents(values, "all").map((item) => item.id)).toEqual([
      "later",
      "earlier",
    ]);
    expect(
      filterEvents(values, "all", "", true).map((item) => item.id),
    ).toEqual(["earlier", "later"]);
  });
  it("filters revisions without losing their actual request text", () => {
    const voice = {
      ...event("voice", "2026-10-30T07:00:00Z", "voice_change"),
      detail: "Please use a younger narrator",
    };
    expect(filterEvents([voice], "voices", "younger")).toEqual([voice]);
    expect(filterEvents([voice], "issues")).toEqual([]);
  });
  it("sums measured work without cache samples or unknown durations", () => {
    expect(
      taskDuration([
        event("work", "", "complete", 12),
        event("cached", "", "cached", 5),
        event("unknown", "", "decision"),
      ]),
    ).toBe(12);
  });
  it("never turns unknown current progress into a percentage", () => {
    expect(
      operationPercent({ current: { percent: null } } as MonitorSnapshot),
    ).toBeNull();
    expect(
      operationPercent({ current: { percent: 120 } } as MonitorSnapshot),
    ).toBe(100);
  });
  it("orders preview rendering before the master and excludes coordinators", () => {
    const jobs = [
      "render:part_001:final",
      "run:preview",
      "provider:image-jobs:1",
      "render:part_001:preview",
      "narration:part_001",
      "preflight:part_001",
    ].map((id) => ({ id, label: id }) as Job);
    expect(orderedJobs(jobs).map((job) => job.id)).toEqual([
      "preflight:part_001",
      "narration:part_001",
      "provider:image-jobs:1",
      "render:part_001:preview",
      "render:part_001:final",
    ]);
  });
  it("requires every part to be delivered before marking a multipart project delivered", () => {
    const base = {
      current: { state: "idle", label: "", message: "", eta: { available: false } },
      assets: { images: 2, shots: 2, reviewed_images: 2, clips: 0, planned_clips: null, provider_requests: 0, deliveries: 1 },
      media: [
        { part: "part_001", master_current: true, preview: { approved: true }, delivered: true },
        { part: "part_002", master_current: true, preview: { approved: true }, delivered: false },
      ],
    } as unknown as MonitorSnapshot;
    expect(isProjectDelivered(base)).toBe(false);
    base.media[1].delivered = true;
    expect(isProjectDelivered(base)).toBe(true);
  });
});

describe("read-only monitor transport", () => {
  afterEach(() => vi.unstubAllGlobals());
  it("rejects partial project responses", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response('{"projects":null}')),
    );
    await expect(fetchProjects(new AbortController().signal)).rejects.toThrow(
      "unavailable",
    );
  });
  it("rejects a stale response belonging to a different project", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            project: { id: "old" },
            current: {},
            media: [],
            events: [],
          }),
        ),
      ),
    );
    await expect(
      fetchSnapshot("selected", new AbortController().signal),
    ).rejects.toThrow("being updated");
  });
  it("passes cancellation and no-store through to fetch", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response('{"projects":[]}'));
    vi.stubGlobal("fetch", fetch);
    const signal = new AbortController().signal;
    expect(await fetchProjects(signal)).toEqual([]);
    expect(fetch).toHaveBeenCalledWith("/api/projects", {
      signal,
      cache: "no-store",
    });
  });
  it("propagates failed responses for the UI to retain its last snapshot", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response("", { status: 503 })),
    );
    await expect(fetchProjects(new AbortController().signal)).rejects.toThrow(
      "503",
    );
  });
});
