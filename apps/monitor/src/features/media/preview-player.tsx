import {
  Film,
  Maximize,
  Pause,
  Play,
  RotateCcw,
  Volume2,
  VolumeX,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";
import { Badge } from "@/components/ui/badge";
import { IconButton } from "@/components/icon-button";
import { SelectField } from "@/components/select-field";
import { SectionPanel } from "@/components/section-panel";
import { timecode } from "@/lib/format";
import type { FilmPart } from "@/types/monitor";
import type { PreviewController } from "./use-preview";

export function PreviewPlayer({
  part,
  controller,
}: {
  part: FilmPart;
  controller: PreviewController;
}) {
  const { loaded, video, playing, time, newVersion, mediaDuration, events } =
    controller;
  const total = mediaDuration || loaded?.duration || 0;
  const available = Boolean(loaded?.preview.url);
  return (
    <SectionPanel
      title="Film preview"
      description="The actual rendered film, ready to watch."
      className="preview-panel"
      contentClassName="p-0!"
      action={
        <Badge variant="outline">
          {part.preview.approved
            ? "Approved version"
            : part.preview.current
              ? "Ready for review"
              : "Preview updating"}
        </Badge>
      }
    >
      <div className="media-player" ref={controller.container}>
        <div className="video-stage">
          <video
            ref={video}
            src={loaded?.preview.url || undefined}
            poster={
              loaded?.preview.current
                ? loaded.shots.find((shot) => shot.image_url)?.image_url ||
                  undefined
                : undefined
            }
            playsInline
            preload="metadata"
            {...events}
            aria-label="Film preview"
          />
          {!available && (
            <div className="media-empty">
              <Film className="size-9" strokeWidth={1.2} />
              <h3>Your preview will appear here</h3>
              <p>
                The player becomes available when a real preview is rendered.
              </p>
            </div>
          )}
          {available && !playing && !controller.error && (
            <Button
              className="center-play"
              size="icon-lg"
              onClick={() => void controller.togglePlay()}
              aria-label="Play film preview"
            >
              <Play className="size-6" fill="currentColor" />
            </Button>
          )}
          {controller.error && (
            <div className="media-error">
              <Film className="size-6" />
              <p>{controller.error}</p>
              {newVersion && (
                <Button size="sm" onClick={controller.loadLatest}>
                  Load latest preview
                </Button>
              )}
            </div>
          )}
        </div>
        <div className="media-controls">
          <Slider
            aria-label="Seek film preview"
            value={[time]}
            min={0}
            max={Math.max(0.01, total)}
            step={0.05}
            disabled={!loaded?.preview.current}
            onValueChange={(value) =>
              controller.seek(Array.isArray(value) ? value[0] : value)
            }
            className="media-seek"
          />
          <div className="media-control-row">
            <div className="flex items-center gap-1">
              <IconButton
                label={playing ? "Pause preview" : "Play preview"}
                disabled={!available}
                onClick={() => void controller.togglePlay()}
              >
                {playing ? (
                  <Pause className="size-4" />
                ) : (
                  <Play className="size-4" />
                )}
              </IconButton>
              <IconButton
                label="Restart preview"
                disabled={!loaded?.preview.current}
                onClick={() => controller.seek(0)}
              >
                <RotateCcw className="size-3.5" />
              </IconButton>
              <span className="player-timecode" data-testid="player-time">
                {timecode(time)} <span>/ {timecode(total)}</span>
              </span>
            </div>
            <div className="flex items-center gap-1.5">
              <IconButton
                label={controller.muted ? "Unmute preview" : "Mute preview"}
                disabled={!available}
                onClick={controller.toggleMute}
              >
                {controller.muted || controller.volume === 0 ? (
                  <VolumeX className="size-4" />
                ) : (
                  <Volume2 className="size-4" />
                )}
              </IconButton>
              <Slider
                aria-label="Preview volume"
                className="volume-slider"
                value={[controller.muted ? 0 : controller.volume]}
                min={0}
                max={1}
                step={0.05}
                disabled={!available}
                onValueChange={(value) =>
                  controller.changeVolume(
                    Array.isArray(value) ? value[0] : value,
                  )
                }
              />
              <SelectField
                label="Playback speed"
                value={controller.speed}
                onChange={controller.changeSpeed}
                options={["0.75", "1", "1.25", "1.5", "2"].map((value) => ({
                  value,
                  label: `${value}×`,
                }))}
                className="playback-speed"
              />
              <IconButton
                label="Full screen preview"
                disabled={!available}
                onClick={controller.fullscreen}
              >
                <Maximize className="size-4" />
              </IconButton>
            </div>
          </div>
        </div>
      </div>
      <div className="preview-footer">
        <span className="version-dot" />
        <span>
          {!available
            ? "Awaiting render"
            : newVersion
              ? "An updated preview is available"
              : !part.preview.current
                ? "Earlier preview · changes pending"
                : "Current preview"}
          {loaded?.preview.version && (
            <span className="ml-2 font-mono text-[10px] text-muted-foreground">
              {loaded.preview.version.slice(0, 8)}
            </span>
          )}
        </span>
        {newVersion && (
          <Button size="sm" variant="outline" onClick={controller.loadLatest}>
            Load updated preview
          </Button>
        )}
      </div>
    </SectionPanel>
  );
}
