import { useState } from "react";
import {
  AudioLines,
  Captions,
  Film,
  Image,
  Minus,
  MousePointer2,
  Plus,
  Volume2,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Slider } from "@/components/ui/slider";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { IconButton } from "@/components/icon-button";
import { SectionPanel } from "@/components/section-panel";
import { timecode } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { FilmPart, TimedItem } from "@/types/monitor";
import type { PreviewController } from "./use-preview";

export interface SelectedClip {
  item: TimedItem;
  kind: "shots" | "speech" | "captions" | "sounds";
}
const tracks = [
  { key: "shots", label: "Shots", icon: Film },
  { key: "speech", label: "Speech", icon: AudioLines },
  { key: "captions", label: "Captions", icon: Captions },
  { key: "sounds", label: "Sound", icon: Volume2 },
] as const;

export function FilmTimeline({
  latest,
  controller,
  onSelect,
}: {
  latest: FilmPart;
  controller: PreviewController;
  onSelect: (clip: SelectedClip) => void;
}) {
  const [zoom, setZoom] = useState(1);
  const part = controller.loaded || latest;
  const total = part.duration || 0;
  const synchronized = Boolean(controller.loaded?.preview.current);
  const activeCaption = synchronized
    ? part.captions.find(
        (cue) => controller.time >= cue.start && controller.time < cue.end,
      )
    : null;
  const activeSpeech = synchronized
    ? part.speech.find(
        (cue) => controller.time >= cue.start && controller.time < cue.end,
      )
    : null;
  const rulerStep =
    total <= 30 ? 5 : total <= 90 ? 10 : Math.ceil(total / 8 / 10) * 10;
  const marks = total
    ? Array.from(
        { length: Math.floor(total / rulerStep) + 1 },
        (_, i) => i * rulerStep,
      )
    : [];
  const ratio = Math.min(1, controller.time / (total || 1));
  return (
    <SectionPanel
      title="Film timeline"
      description={
        synchronized
          ? controller.newVersion
            ? "Loaded preview timing · a newer version is available."
            : "Measured shots, speech, captions and sound. Select any clip to inspect it."
          : "Current production timing · synchronized seeking is available with a current preview."
      }
      className="film-timeline"
      contentClassName="p-0!"
      action={
        <div className="timeline-zoom">
          <IconButton
            label="Zoom out timeline"
            onClick={() => setZoom((value) => Math.max(1, value - 0.5))}
            disabled={zoom <= 1}
          >
            <Minus className="size-3" />
          </IconButton>
          <Slider
            aria-label="Timeline zoom"
            min={1}
            max={4}
            step={0.5}
            value={[zoom]}
            onValueChange={(value) =>
              setZoom(Array.isArray(value) ? value[0] : value)
            }
          />
          <IconButton
            label="Zoom in timeline"
            onClick={() => setZoom((value) => Math.min(4, value + 0.5))}
            disabled={zoom >= 4}
          >
            <Plus className="size-3" />
          </IconButton>
        </div>
      }
    >
      <div className="timeline-scroll">
        <div
          className="timeline-canvas"
          style={{ minWidth: 740, width: `${zoom * 100}%` }}
        >
          <div className="timeline-ruler">
            {marks.map((mark) => (
              <Button
                key={mark}
                variant="ghost"
                size="xs"
                style={{ left: `${(mark / total) * 100}%` }}
                onClick={() => controller.seek(mark)}
                aria-label={`Seek to ${timecode(mark)}`}
              >
                {timecode(mark)}
              </Button>
            ))}
          </div>
          {tracks.map((track) => (
            <div className="film-track-row" key={track.key}>
              <div className="film-track-label">
                <track.icon className="size-3.5" />
                <span>{track.label}</span>
                <small>{part[track.key].length}</small>
              </div>
              <div
                className={cn("film-track", `track-${track.key}`)}
                data-testid={`track-${track.key}`}
              >
                {part[track.key]
                  .filter(
                    (item) =>
                      Number.isFinite(item.start) &&
                      Number.isFinite(item.end) &&
                      item.end > item.start &&
                      total > 0,
                  )
                  .map((item, index) => {
                    const name =
                      track.key === "shots"
                        ? item.id?.replace("SHOT-", "") || `Shot ${index + 1}`
                        : track.key === "speech"
                          ? part.voices.find(
                              (voice) => voice.speaker === item.speaker,
                            )?.name || item.speaker
                          : item.text || item.role;
                    const active =
                      synchronized &&
                      controller.time >= item.start &&
                      controller.time < item.end;
                    return (
                      <Tooltip key={item.id || `${item.start}-${index}`}>
                        <TooltipTrigger
                          render={
                            <Button
                              variant="ghost"
                              className={cn(
                                "timeline-clip",
                                `clip-${track.key}`,
                                active && "clip-active",
                              )}
                              style={{
                                left: `${(item.start / total) * 100}%`,
                                width: `${((item.end - item.start) / total) * 100}%`,
                              }}
                              onClick={() => {
                                onSelect({ item, kind: track.key });
                                controller.seek(item.start);
                              }}
                              aria-label={`${track.label}: ${name} from ${timecode(item.start)} to ${timecode(item.end)}`}
                            />
                          }
                        >
                          {track.key === "shots" && item.image_url && (
                            <img
                              src={item.image_url}
                              alt=""
                              loading="lazy"
                              onError={(event) => {
                                event.currentTarget.style.visibility = "hidden";
                              }}
                            />
                          )}
                          <span>{name}</span>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">
                          <div>
                            <strong className="block text-xs">{name}</strong>
                            <span className="mt-1 block opacity-70">
                              {timecode(item.start)} – {timecode(item.end)}
                            </span>
                          </div>
                        </TooltipContent>
                      </Tooltip>
                    );
                  })}
                {!part[track.key].length && (
                  <span className="track-empty">
                    {track.key === "sounds"
                      ? "No additional sound cues recorded"
                      : "No measured clips recorded"}
                  </span>
                )}
              </div>
            </div>
          ))}
          {synchronized && (
            <div
              className="film-playhead"
              style={{ left: `calc(${ratio * 100}% + ${80 * (1 - ratio)}px)` }}
            >
              <span>{timecode(controller.time)}</span>
            </div>
          )}
        </div>
      </div>
      <div className="timeline-bottom">
        <span>
          <MousePointer2 className="size-3" />
          Click a clip to inspect{synchronized ? " and seek" : ""}
        </span>
        <Badge variant="outline">{timecode(total)} total</Badge>
      </div>
      <div className="current-line">
        <span className="eyebrow">
          <Captions className="size-3" />
          CURRENT LINE
        </span>
        <p>
          {!synchronized
            ? "A current preview is needed to follow the measured speech and captions."
            : (
                activeCaption?.text ||
                activeSpeech?.text ||
                "No spoken line at this time."
              ).replaceAll("\n", " ")}
        </p>
      </div>
    </SectionPanel>
  );
}

export function ClipInspector({ clip }: { clip: SelectedClip | null }) {
  return (
    <SectionPanel
      title="Clip inspector"
      description="The selected clip’s actual timing and content."
    >
      {clip ? (
        <div className="clip-inspector">
          <div className="mb-4 flex items-center justify-between">
            <Badge variant="outline" className="capitalize">
              {clip.kind}
            </Badge>
            <span className="font-mono text-xs text-muted-foreground">
              {timecode(clip.item.start)} – {timecode(clip.item.end)}
            </span>
          </div>
          {clip.item.image_url && (
            <img
              src={clip.item.image_url}
              alt={clip.item.description || "Selected shot"}
              className="mb-4 aspect-video w-full rounded object-cover"
            />
          )}
          <h3>{clip.item.id || "Selected clip"}</h3>
          <p>
            {clip.item.description ||
              clip.item.text ||
              clip.item.narration ||
              clip.item.role ||
              "No additional written detail was recorded."}
          </p>
          <dl>
            <div>
              <dt>Start</dt>
              <dd>{clip.item.start.toFixed(3)} sec</dd>
            </div>
            <div>
              <dt>End</dt>
              <dd>{clip.item.end.toFixed(3)} sec</dd>
            </div>
            <div>
              <dt>Duration</dt>
              <dd>{(clip.item.end - clip.item.start).toFixed(3)} sec</dd>
            </div>
            {clip.item.voice && (
              <div>
                <dt>Voice</dt>
                <dd>{clip.item.voice}</dd>
              </div>
            )}
          </dl>
        </div>
      ) : (
        <div className="empty-inline">
          <Image className="size-6" />
          <h3>Select a clip</h3>
          <p>Choose a shot, spoken line, caption or sound from the timeline.</p>
        </div>
      )}
    </SectionPanel>
  );
}
