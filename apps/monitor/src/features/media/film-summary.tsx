import { ArrowUpRight, Film, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { SectionPanel } from "@/components/section-panel";
import { partLabel, timecode } from "@/lib/format";
import type { FilmPart } from "@/types/monitor";

export function FilmSummary({
  part,
  open,
}: {
  part: FilmPart | null;
  open: () => void;
}) {
  const image = part?.preview.current
    ? part.shots.find((shot) => shot.image_url)?.image_url
    : null;
  return (
    <SectionPanel
      title="Film preview"
      action={
        <Badge variant="outline">
          {part ? partLabel(part.part) : "Not planned"}
        </Badge>
      }
      contentClassName="compact-preview-content"
    >
      <Button
        variant="ghost"
        className="preview-thumbnail"
        onClick={open}
        aria-label="Open film preview and timeline"
      >
        {image ? (
          <img src={image} alt="Current film shot" />
        ) : (
          <Film className="size-7" strokeWidth={1.3} />
        )}
        <span className="thumbnail-play">
          <Play className="size-4" fill="currentColor" />
        </span>
        {part?.duration && (
          <span className="thumbnail-duration">{timecode(part.duration)}</span>
        )}
      </Button>
      <div className="compact-preview-footer">
        <span>
          {part?.preview.approved
            ? "Approval recorded"
            : part?.preview.current
              ? "Ready for your review"
              : "Preview in progress"}
        </span>
        <Button variant="ghost" size="xs" onClick={open}>
          Open workspace <ArrowUpRight className="size-3" />
        </Button>
      </div>
    </SectionPanel>
  );
}
