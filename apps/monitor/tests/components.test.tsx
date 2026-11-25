import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { CurrentOperation } from "../src/features/production/current-operation";
import { CastWorkspace } from "../src/features/cast/cast-workspace";
import type { MonitorSnapshot } from "../src/types/monitor";

function snapshotFixture(partialDelivered = false): MonitorSnapshot {
  return {
    project: {
      id: "proj-1",
      title: "Multipart Story",
      branch: "story/multipart",
      workspace: "/tmp/ws",
      path: "/tmp/ws/stories/multipart",
    },
    observed_at: "2026-11-25T05:00:00Z",
    updated_at: "2026-11-25T05:00:00Z",
    state: "idle",
    current: {
      label: "Selected local steps finished",
      message: "Part 2 still awaits export.",
      state: "idle",
      eta: { available: false, reason: "No active operation" },
    },
    jobs: [],
    steps: { done: 2, total: 2, scope: "selected local steps" },
    parts: [
      {
        id: "part_001",
        title: "Part 1",
        images: { done: 1, total: 1, reviewed: 1 },
        voice: { done: 0, total: null, applicable: false },
        preview: true,
        master: true,
        duration_seconds: 10,
      },
      {
        id: "part_002",
        title: "Part 2",
        images: { done: 1, total: 1, reviewed: 1 },
        voice: { done: 0, total: null, applicable: false },
        preview: true,
        master: true,
        duration_seconds: 10,
      },
    ],
    attention: [],
    events: [],
    media: [
      {
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
          version: "abc",
          reasons: [],
          url: "/api/media?part=part_001",
          review_state: "approved",
          at: 1,
        },
        master_exists: true,
        master_current: true,
        delivered: true,
      },
      {
        part: "part_002",
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
          version: "def",
          reasons: [],
          url: "/api/media?part=part_002",
          review_state: "approved",
          at: 1,
        },
        master_exists: true,
        master_current: true,
        delivered: !partialDelivered,
      },
    ],
    remaining_local: { available: false, reason: "Idle" },
    run: { profile: null, status: null, started_at: null, finished_at: null },
    since_intake_seconds: 60,
    assets: {
      images: 2,
      shots: 2,
      reviewed_images: 2,
      clips: 0,
      planned_clips: null,
      provider_requests: 0,
      deliveries: 1,
    },
    warnings: [],
    read_only: true,
    cast: {
      total: 1,
      ready: 1,
      pending_changes: 0,
      scope: "Cast sheets",
      characters: [
        {
          id: "CHAR-001",
          name: "Amina",
          revision: "r1",
          style_id: "STYLE-001",
          style_revision: "r1",
          state: "ready",
          issues: [],
          design_version: "v1",
          images: [],
          review: null,
          review_current: true,
          changes: [],
          linked_shots: ["part_001/SHOT-001"],
          legacy_document: null,
          profile: {
            name: "Amina",
            revision: "r1",
            style_id: "STYLE-001",
            style_revision: "r1",
            role: "Courier",
            age_or_life_stage: "Adult",
            design_type: "Human",
            personality: "Steady",
            appearance: "Wool coat",
            proportions: "Natural",
            wardrobe: "Navy coat",
            relative_scale: "Average",
            expression_system: "Subtle",
            identity_anchors: ["Brass badge"],
            views: ["front"],
            expressions: { calm: "Steady gaze" },
            poses: { standing: "Holding satchel" },
            reference_notes: "Keep the brass badge on the left lapel.",
          },
        },
      ],
    },
  };
}

describe("Monitor component rendering", () => {
  it("does not render Delivered badge prematurely when part_002 is not delivered", () => {
    const partialHtml = renderToStaticMarkup(
      <CurrentOperation snapshot={snapshotFixture(true)} navigate={() => {}} />,
    );
    expect(partialHtml).not.toContain(">Delivered<");

    const completeHtml = renderToStaticMarkup(
      <CurrentOperation snapshot={snapshotFixture(false)} navigate={() => {}} />,
    );
    expect(completeHtml).toContain(">Delivered<");
  });

  it("renders cast workspace summary and character rows without crashing", () => {
    const html = renderToStaticMarkup(
      <CastWorkspace
        snapshot={snapshotFixture(false)}
        connected={true}
        refresh={() => {}}
      />,
    );
    expect(html).toContain("Amina");
    expect(html).toContain("CHAR-001");
  });
});
