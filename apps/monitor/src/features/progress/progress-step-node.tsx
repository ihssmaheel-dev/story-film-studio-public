import { memo } from "react";
import { Handle, Position, type Node, type NodeProps } from "@xyflow/react";
import {
  AudioLines,
  Captions,
  Check,
  Clapperboard,
  Clock3,
  FileCheck2,
  FileText,
  Image,
  Layers3,
  LoaderCircle,
  Mic2,
  PackageCheck,
  ScanLine,
  Settings2,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Volume2,
  Workflow,
  UsersRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { duration, partLabel, stateLabels, timestamp } from "@/lib/format";
import { cn } from "@/lib/utils";
import {
  displayState,
  isActive,
  isDone,
  type ProgressStep,
} from "./progress-model";

export type StepNode = Node<
  { step: ProgressStep; connected: boolean; openDetails: (id: string) => void },
  "productionStep"
>;
export function StepIcon({ stage }: { stage: string }) {
  const icons = {
    intake: FileText,
    story: FileCheck2,
    world: Sparkles,
    cast: UsersRound,
    shots: Layers3,
    images: Image,
    casting: AudioLines,
    voice_setup: Settings2,
    audition: Mic2,
    narration: Mic2,
    alignment: ScanLine,
    timeline: Layers3,
    sound: Volume2,
    mix: AudioLines,
    subtitles: Captions,
    preview: Clapperboard,
    review: FileCheck2,
    master: Clapperboard,
    qa: ShieldCheck,
    delivery: PackageCheck,
  };
  const Icon = icons[stage as keyof typeof icons] || Workflow;
  return <Icon className="size-4" strokeWidth={1.7} />;
}

export const ProgressStepNode = memo(function ProgressStepNode({
  data,
  selected,
}: NodeProps<StepNode>) {
  const { step, connected } = data;
  const state = displayState(step.state, connected),
    active = isActive(state);
  const label =
    !connected && isActive(step.state)
      ? "Last reported activity"
      : step.statusLabel || stateLabels[state] || state;
  const Icon = active
    ? LoaderCircle
    : isDone(state)
      ? Check
      : ["failed", "interrupted", "stale"].includes(state)
        ? TriangleAlert
        : Clock3;
  return (
    <>
      {(["left", "right", "top"] as const).map((side) => (
        <Handle
          key={`in-${side}`}
          id={`in-${side}`}
          type="target"
          position={
            Position[
              side === "left" ? "Left" : side === "right" ? "Right" : "Top"
            ]
          }
          className="progress-node-handle"
        />
      ))}
      {(["left", "right", "bottom"] as const).map((side) => (
        <Handle
          key={`out-${side}`}
          id={`out-${side}`}
          type="source"
          position={
            Position[
              side === "left" ? "Left" : side === "right" ? "Right" : "Bottom"
            ]
          }
          className="progress-node-handle"
        />
      ))}
      <Button
        variant="ghost"
        className={cn(
          "progress-step nodrag nopan",
          active && "progress-step-active",
          isDone(state) && "progress-step-done",
          ["failed", "interrupted", "stale"].includes(state) &&
            "progress-step-issue",
          selected && "progress-step-selected",
        )}
        onClick={() => data.openDetails(step.id)}
        aria-label={`${step.title}: ${label}. Open details`}
        aria-busy={active}
        data-testid={`progress-step-${step.stage}`}
      >
        <div className="progress-step-heading">
          <span className="progress-stage-icon">
            <StepIcon stage={step.stage} />
          </span>
          <div>
            <strong>{step.title}</strong>
            <small>{step.part ? partLabel(step.part) : "Project-wide"}</small>
          </div>
          {step.isCurrent && (
            <span className="progress-current-tag">
              {connected ? "CURRENT" : "LAST KNOWN"}
            </span>
          )}
        </div>
        <div className="progress-step-state">
          <span className={cn(active && "progress-live-state")}>
            <Icon
              className={cn("size-3", active && "motion-safe:animate-spin")}
              data-testid={active ? "step-running-loader" : undefined}
              aria-hidden="true"
            />
            {label}
          </span>
          {step.total != null && (
            <small>
              {step.completed ?? 0}/{step.total} {step.unit}
            </small>
          )}
        </div>
        <div className="progress-step-time">
          <span>
            {step.finishedAt
              ? timestamp(step.finishedAt)
              : step.startedAt
                ? `Started ${timestamp(step.startedAt)}`
                : step.events[0]?.at
                  ? `Recorded ${timestamp(step.events[0].at)}`
                  : "Time not recorded"}
          </span>
          <span>
            {step.duration != null ? duration(step.duration, true) : "—"}
          </span>
        </div>
        {step.percent != null && (
          <Progress
            value={step.percent}
            className="progress-node-meter"
            aria-label={`${step.title} measured progress`}
          />
        )}
      </Button>
    </>
  );
});
