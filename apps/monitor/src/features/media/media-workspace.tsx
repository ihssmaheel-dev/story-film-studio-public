import { useState } from "react";
import {
  ArrowUpRight,
  Check,
  Circle,
  CircleAlert,
  Eye,
  FileCheck2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SectionPanel } from "@/components/section-panel";
import { SelectField } from "@/components/select-field";
import { VoicesSummary } from "@/features/voices/voices-panel";
import { partLabel } from "@/lib/format";
import type { FilmPart, MonitorSnapshot } from "@/types/monitor";
import { PreviewPlayer } from "./preview-player";
import { usePreview } from "./use-preview";
import {
  ClipInspector,
  FilmTimeline,
  type SelectedClip,
} from "./film-timeline";

function ReviewStatus({ part, watch }: { part: FilmPart; watch: () => void }) {
  const voiceReady =
    !part.requires_speech ||
    (part.voices.length > 0 && part.voices.every((voice) => voice.current));
  const title = part.preview.approved
    ? "Your preview is approved"
    : part.preview.current
      ? "Ready for your review"
      : !voiceReady
        ? "Updating the voice performance"
        : "Preparing the current preview";
  const steps = [
    { label: "Selected voices applied", done: voiceReady },
    { label: "Current preview rendered", done: part.preview.current },
    { label: "Your preview decision", done: part.preview.approved },
    { label: "Current master file", done: part.master_current },
  ];
  return (
    <SectionPanel
      title="Review & delivery"
      description="What is ready, and what happens next."
      action={
        <span className="review-icon">
          <FileCheck2 className="size-4" />
        </span>
      }
    >
      <h3 className="review-title">{title}</h3>
      <p className="review-description">
        {part.preview.approved
          ? "Your decision is recorded for this exact preview."
          : part.preview.current
            ? "Watch the updated voices, imagery, pacing and captions. Share your decision or changes with the production agent."
            : part.preview.reasons.join(". ") ||
              "Production records will show the next step when available."}
      </p>
      <div className="review-checklist">
        {steps.map((step) => (
          <div key={step.label} className={step.done ? "done" : ""}>
            {step.done ? (
              <Check className="size-3.5" />
            ) : (
              <Circle className="size-3.5" />
            )}
            <span>{step.label}</span>
            <small>{step.done ? "Recorded" : "Pending"}</small>
          </div>
        ))}
      </div>
      {part.preview.exists && (
        <Button className="w-full" onClick={watch}>
          <Eye className="size-3.5" />
          {part.preview.approved
            ? "Watch approved preview"
            : part.preview.current
              ? "Review this preview"
              : "Compare earlier preview"}
          <ArrowUpRight className="ml-auto size-3.5" />
        </Button>
      )}
    </SectionPanel>
  );
}

function PartWorkspace({
  part,
  snapshot,
  expanded,
}: {
  part: FilmPart;
  snapshot: MonitorSnapshot;
  expanded: boolean;
}) {
  const controller = usePreview(part);
  const [clip, setClip] = useState<SelectedClip | null>(null);
  function watch() {
    if (controller.newVersion) controller.loadLatest();
    controller.container.current?.scrollIntoView({
      block: "center",
      behavior: matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "instant"
        : "smooth",
    });
    controller.container.current
      ?.querySelector<HTMLElement>('[aria-label="Play preview"]')
      ?.focus();
  }
  return (
    <div
      className={
        expanded ? "media-workspace expanded-workspace" : "media-workspace"
      }
    >
      <div className="preview-grid">
        <PreviewPlayer part={part} controller={controller} />
        <div className="preview-aside">
          <ReviewStatus part={part} watch={watch} />
          {expanded ? (
            <ClipInspector clip={clip} />
          ) : (
            <VoicesSummary part={part} />
          )}
        </div>
      </div>
      <FilmTimeline latest={part} controller={controller} onSelect={setClip} />
      {!expanded && snapshot.attention.length > 0 && (
        <SectionPanel
          title="Needs attention"
          description="Real decisions and studio tasks that affect the next step."
          action={<Badge variant="outline">{snapshot.attention.length}</Badge>}
        >
          <div className="attention-list">
            {snapshot.attention.map((item, index) => (
              <div key={`${item.kind}-${index}`}>
                <CircleAlert className="size-4" />
                <div>
                  <strong>
                    {item.actor === "user"
                      ? "Your decision"
                      : item.actor === "provider"
                        ? "Provider result"
                        : "Studio action"}
                  </strong>
                  <p>{item.message}</p>
                </div>
              </div>
            ))}
          </div>
        </SectionPanel>
      )}
    </div>
  );
}

export function MediaWorkspace({
  snapshot,
  expanded = false,
}: {
  snapshot: MonitorSnapshot;
  expanded?: boolean;
}) {
  const [selection, setSelection] = useState(snapshot.media[0]?.part || "");
  const part =
    snapshot.media.find((item) => item.part === selection) || snapshot.media[0];
  if (!part)
    return (
      <SectionPanel
        title="Film workspace"
        description="Your preview and timeline will appear as production is recorded."
      >
        <div className="empty-inline">
          <Eye className="size-7" />
          <h3>No film part is planned yet</h3>
          <p>
            Measured shots, speech and captions will appear here when they
            exist.
          </p>
        </div>
      </SectionPanel>
    );
  return (
    <section className="space-y-4" aria-label="Film workspace">
      <div className="media-section-label">
        <div>
          <span className="eyebrow">FILM WORKSPACE</span>
          <span className="text-xs text-muted-foreground">
            {part.shots.length} shots <span className="mx-1">/</span>{" "}
            {part.speech.length} speech turns <span className="mx-1">/</span>{" "}
            {part.captions.length} captions
          </span>
        </div>
        <SelectField
          label="Select film part"
          value={part.part}
          onChange={setSelection}
          options={snapshot.media.map((item) => ({
            value: item.part,
            label: partLabel(item.part),
          }))}
        />
      </div>
      <PartWorkspace
        key={`${snapshot.project.id}:${part.part}`}
        part={part}
        snapshot={snapshot}
        expanded={expanded}
      />
    </section>
  );
}
