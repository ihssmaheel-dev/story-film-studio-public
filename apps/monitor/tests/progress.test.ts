import { describe, expect, it } from "vitest";
import {
  buildProgressSteps,
  displayState,
  isActive,
  stepLayout,
} from "../src/features/progress/progress-model";
import type {
  FilmPart,
  Job,
  MonitorSnapshot,
  ProductionEvent,
  CastCharacter,
} from "../src/types/monitor";

function snapshot(): MonitorSnapshot {
  return {
    project: {
      id: "fixture",
      title: "Synthetic progress",
      branch: "story/fixture",
      path: "",
      workspace: "",
    },
    observed_at: "2026-10-30T10:00:00Z",
    updated_at: null,
    state: "idle",
    current: {
      label: "Ready",
      state: "idle",
      message: "",
      eta: { available: false },
    },
    jobs: [],
    events: [],
    parts: [],
    media: [],
    attention: [],
    steps: { done: 0, total: null, scope: "" },
    remaining_local: { available: false },
    run: { profile: null, status: null, started_at: null, finished_at: null },
    since_intake_seconds: null,
    assets: {
      images: 0,
      shots: 0,
      reviewed_images: 0,
      clips: 0,
      planned_clips: null,
      provider_requests: 0,
      deliveries: 0,
    },
    warnings: [],
    read_only: true,
  };
}

describe("actual cast-sheet progress", () => {
  function character(id: string, state: string): CastCharacter {
    return {
      id,
      name: id,
      revision: "r1",
      style_id: "STYLE-001",
      style_revision: "r1",
      state,
      issues: [],
      profile: null,
      legacy_document: null,
      design_version: "actual-design-version",
      images: [],
      review: null,
      review_current: false,
      changes: [],
      linked_shots: [],
    };
  }
  it("counts only inspected characters and keeps missing profiles distinct from generation", () => {
    const value = snapshot();
    value.cast = {
      total: 2,
      ready: 0,
      pending_changes: 0,
      characters: [
        character("CHAR-001", "profile_missing"),
        character("CHAR-002", "awaiting_review"),
      ],
      scope: "fixture",
    };
    const cast = buildProgressSteps(value, "part_001").find(
      (step) => step.stage === "cast",
    )!;
    expect(cast.state).toBe("waiting");
    expect(cast.completed).toBe(0);
    expect(cast.percent).toBe(0);
    expect(isActive(cast.state)).toBe(false);
    expect(cast.eta.available).toBe(false);
  });
  it("has one project-wide step for real provider work and stops its activity offline", () => {
    const value = snapshot();
    value.cast = {
      total: 1,
      ready: 0,
      pending_changes: 0,
      characters: [character("CHAR-001", "provider_wait")],
      scope: "fixture",
    };
    value.jobs = [
      { ...job("cast:provider:actual", "provider_wait"), part: null },
    ];
    value.events = [
      {
        id: "cast-change",
        at: "2026-11-02T10:00:00Z",
        kind: "cast_change",
        job: "cast:CHAR-001",
        label: "Character revision",
        message: "Actual fixture request",
        part: null,
      },
    ];
    const cast = buildProgressSteps(value, "part_001").filter(
      (step) => step.stage === "cast",
    );
    expect(cast).toHaveLength(1);
    expect(cast[0].part).toBeNull();
    expect(displayState(cast[0].state, false)).toBe("reported");
    value.cast.ready = 1;
    value.cast.characters[0].state = "ready";
    value.jobs = [];
    expect(
      buildProgressSteps(value, "part_001").find(
        (step) => step.stage === "cast",
      )?.state,
    ).toBe("complete");
  });
});
function job(id = "narration:part_001", state = "complete"): Job {
  return {
    id,
    label: id,
    part: "part_001",
    state,
    message: "Actual synthetic task record",
    elapsed_seconds: 12.5,
    eta: { available: false },
  };
}
function film(): FilmPart {
  return {
    part: "part_001",
    duration: 10,
    shots: [],
    speech: [],
    captions: [],
    sounds: [],
    voices: [],
    voice_changes: [],
    requires_speech: false,
    preview: {
      exists: true,
      current: true,
      approved: true,
      version: "fixture",
      url: "/synthetic.mp4",
      reasons: [],
      review_state: "approved",
      at: null,
    },
    master_exists: true,
    master_current: true,
  };
}
function event(id: string, at: string): ProductionEvent {
  return {
    id,
    at,
    job: "narration:part_001",
    kind: "complete",
    label: "Voice performance",
    message: "Synthetic voice task",
    part: "part_001",
    duration_seconds: 2,
  };
}

describe("recorded progress projection", () => {
  it("does not hide a failed image job behind older available image files", () => {
    const value = snapshot();
    value.jobs = [job("images:part_001", "failed")];
    value.parts = [
      {
        id: "part_001",
        title: "Synthetic part",
        images: { done: 1, total: 1, reviewed: 1 },
        voice: { done: 0, total: null, applicable: false },
        preview: false,
        master: false,
        duration_seconds: null,
      },
    ];
    expect(
      buildProgressSteps(value, "part_001").find(
        (step) => step.stage === "images",
      )?.state,
    ).toBe("failed");
  });
  it("does not invent tasks in an empty project", () => {
    expect(buildProgressSteps(snapshot(), "part_001")).toEqual([]);
  });
  it("shows only recorded tasks, preserving unknown progress and measured durations", () => {
    const value = snapshot();
    value.jobs = [job()];
    const steps = buildProgressSteps(value, "part_001");
    expect(steps).toHaveLength(1);
    expect(steps[0]).toMatchObject({
      stage: "narration",
      duration: 12.5,
      percent: null,
      completed: null,
      total: null,
    });
  });
  it("maps the actual running counter and current job without adding an ETA", () => {
    const value = snapshot();
    value.jobs = [
      {
        ...job("narration:part_001", "running"),
        completed: 2,
        total: 8,
        percent: 25,
        unit: "clips",
      },
    ];
    value.current = value.jobs[0];
    expect(buildProgressSteps(value, "part_001")[0]).toMatchObject({
      state: "running",
      isCurrent: true,
      percent: 25,
      eta: { available: false },
    });
  });
  it("preserves node identity when a task completes", () => {
    const value = snapshot();
    value.jobs = [job("narration:part_001", "running")];
    const before = buildProgressSteps(value, "part_001")[0];
    value.jobs[0].state = "complete";
    const after = buildProgressSteps(value, "part_001")[0];
    expect(after.id).toBe(before.id);
    expect(isActive(after.state)).toBe(false);
  });
  it("does not turn reported or stale work into a live task", () => {
    expect(isActive("reported")).toBe(false);
    expect(isActive("stale")).toBe(false);
    expect(displayState("running", false)).toBe("reported");
    expect(displayState("provider_wait", false)).toBe("reported");
  });
  it("marks old speech stale after an actual selected-voice change", () => {
    const value = snapshot(),
      part = film();
    part.requires_speech = true;
    part.voices = [
      {
        speaker: "NARRATOR",
        name: "Narrator",
        provider: "kokoro",
        voice: "new",
        model: "kokoro-82m",
        rendered_voices: ["old"],
        clips: 1,
        expected_clips: 1,
        current: false,
      },
    ];
    value.media = [part];
    value.jobs = [job()];
    expect(
      buildProgressSteps(value, "part_001").find(
        (step) => step.stage === "narration",
      )?.state,
    ).toBe("stale");
  });
  it("shows a human preview decision as waiting rather than approved", () => {
    const value = snapshot(),
      part = film();
    part.preview.approved = false;
    value.media = [part];
    value.current.state = "waiting";
    expect(
      buildProgressSteps(value, "part_001").find(
        (step) => step.stage === "review",
      ),
    ).toMatchObject({
      state: "waiting",
      statusLabel: "Your decision",
      isCurrent: true,
      finishedAt: null,
    });
  });
  it("does not let older render receipts conceal a stale preview and master", () => {
    const value = snapshot(),
      part = film();
    part.preview.current = false;
    part.preview.approved = false;
    part.master_current = false;
    value.media = [part];
    value.jobs = [job("render:part_001:preview"), job("render:part_001:final")];
    const steps = buildProgressSteps(value, "part_001");
    expect(steps.find((step) => step.stage === "preview")?.state).toBe("stale");
    expect(steps.find((step) => step.stage === "master")?.state).toBe("stale");
  });
  it("preserves a verified running render while an earlier preview is stale", () => {
    const value = snapshot(),
      part = film();
    part.preview.current = false;
    value.media = [part];
    value.jobs = [job("render:part_001:preview", "running")];
    value.current = value.jobs[0];
    expect(
      buildProgressSteps(value, "part_001").find(
        (step) => step.stage === "preview",
      )?.state,
    ).toBe("running");
  });
  it("keeps cached rendering distinct from a new render", () => {
    const value = snapshot();
    value.media = [film()];
    value.jobs = [job("render:part_001:preview", "cached")];
    expect(
      buildProgressSteps(value, "part_001").find(
        (step) => step.stage === "preview",
      ),
    ).toMatchObject({ state: "cached", statusLabel: "Reused" });
  });
  it("does not display another part’s job or events as the selected part", () => {
    const value = snapshot();
    value.jobs = [
      job(),
      { ...job("render:part_002:preview"), part: "part_002" },
    ];
    value.events = [
      { ...event("other", "2026-10-30T10:00:00Z"), part: "part_002" },
    ];
    const steps = buildProgressSteps(value, "part_001");
    expect(steps).toHaveLength(1);
    expect(steps[0].events).toEqual([]);
  });
  it("retains provider waiting without making up a heartbeat or percentage", () => {
    const value = snapshot();
    value.jobs = [
      {
        ...job("provider:image-jobs:request", "provider_wait"),
        part: null,
        elapsed_seconds: 22,
      },
    ];
    value.current = value.jobs[0];
    expect(buildProgressSteps(value, "part_001")[0]).toMatchObject({
      state: "provider_wait",
      isCurrent: true,
      percent: null,
      eta: { available: false },
    });
  });
  it("exposes unresolved project actions even when recorded files are complete", () => {
    const value = snapshot();
    value.current.state = "waiting";
    value.attention = [
      {
        kind: "error",
        actor: "agent",
        message: "Reconcile the actual unknown provider outcome",
      },
    ];
    expect(buildProgressSteps(value, "part_001")[0]).toMatchObject({
      stage: "attention",
      state: "failed",
      isCurrent: true,
    });
  });
  it("orders the selected step evidence by actual timestamps", () => {
    const value = snapshot();
    value.events = [
      event("earlier", "2026-10-30T12:30:00+05:30"),
      event("later", "2026-10-30T07:01:00Z"),
    ];
    expect(
      buildProgressSteps(value, "part_001")[0].events.map((item) => item.id),
    ).toEqual(["later", "earlier"]);
  });
  it("uses a stable compact layout with vertical turns between rows", () => {
    expect(stepLayout(3, 4)).toEqual({ x: 714, y: 0 });
    expect(stepLayout(4, 4)).toEqual({ x: 714, y: 136 });
    expect(stepLayout(7, 4)).toEqual({ x: 0, y: 136 });
    expect(stepLayout(2, 1)).toEqual({ x: 0, y: 272 });
  });
});
