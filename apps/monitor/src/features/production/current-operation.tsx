import {
  Activity,
  ArrowRight,
  CircleCheck,
  Clock3,
  Hourglass,
  Image,
  Mic2,
  Workflow,
} from "lucide-react";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/status-badge";
import { duration, relative, timestamp } from "@/lib/format";
import { operationPercent } from "@/lib/selectors";
import type { MonitorSnapshot, Section } from "@/types/monitor";

export function CurrentOperation({
  snapshot,
  navigate,
}: {
  snapshot: MonitorSnapshot;
  navigate: (section: Section) => void;
}) {
  const { current, assets, steps } = snapshot;
  const percent = operationPercent(snapshot);
  const eta = current.eta;
  const delivered =
    current.state === "idle" &&
    assets.deliveries > 0 &&
    snapshot.media.length > 0 &&
    snapshot.media.every(
      (part) => part.master_current && part.preview.approved,
    );
  const Icon = delivered ? CircleCheck : Activity;
  return (
    <>
      <Card className="current-operation">
        <div className="current-main">
          <div className="operation-icon">
            <Icon className="size-5" strokeWidth={1.6} />
          </div>
          <div className="min-w-0 flex-1">
            <div className="mb-2 flex flex-wrap items-center gap-2">
              <span className="eyebrow">CURRENT ACTIVITY</span>
              <StatusBadge
                state={delivered ? "complete" : current.state}
                label={delivered ? "Delivered" : undefined}
              />
            </div>
            <h2 className="current-title">{current.label}</h2>
            <p className="current-description">{current.message}</p>
            {percent !== null && (
              <div className="mt-4 max-w-xl">
                <Progress
                  value={percent}
                  aria-label="Current operation progress"
                />
                <div className="mt-2 flex justify-between text-xs text-muted-foreground">
                  <span>
                    {current.completed?.toLocaleString(undefined, {
                      maximumFractionDigits: 1,
                    })}{" "}
                    /{" "}
                    {current.total?.toLocaleString(undefined, {
                      maximumFractionDigits: 1,
                    })}{" "}
                    {current.unit}
                  </span>
                  <span>{Math.round(percent)}%</span>
                </div>
              </div>
            )}
            <div className="operation-meta">
              <span>
                <Clock3 className="size-3" />
                {snapshot.updated_at
                  ? `Updated ${timestamp(snapshot.updated_at)}`
                  : "Awaiting a recorded update"}
              </span>
              {current.state === "running" && (
                <span>
                  <Activity className="size-3" />
                  Heartbeat {duration(current.heartbeat_age_seconds)} ago
                </span>
              )}
              {(current.progress_age_seconds || 0) > 60 &&
                current.state === "running" && (
                  <span>
                    No measured change for{" "}
                    {duration(current.progress_age_seconds)}
                  </span>
                )}
            </div>
          </div>
        </div>
        <div className="operation-time">
          <span className="eyebrow">
            <Hourglass className="size-3" />
            TIME REMAINING
          </span>
          <strong>
            {eta.available
              ? `${duration(eta.low_seconds)} – ${duration(eta.high_seconds)}`
              : current.state === "running"
                ? "Measuring…"
                : delivered
                  ? "Work completed"
                  : "Not estimated"}
          </strong>
          <p>
            {eta.available
              ? eta.basis
              : current.state === "running"
                ? eta.reason
                : delivered
                  ? "No production task is currently running."
                  : "An estimate appears when a measured task is running."}
          </p>
          {current.elapsed_seconds != null && (
            <span className="time-elapsed">
              {duration(current.elapsed_seconds)} elapsed in this task
            </span>
          )}
          <Button
            variant="link"
            size="sm"
            className="progress-link"
            onClick={() => navigate("progress")}
          >
            View production progress <ArrowRight className="size-3" />
          </Button>
        </div>
      </Card>
      <div className="metric-grid">
        {[
          {
            title: "Story images",
            value: `${assets.images} / ${assets.shots}`,
            note: `${assets.reviewed_images} visual reviews recorded`,
            icon: Image,
            tone: "purple",
          },
          {
            title: "Voice performance",
            value: assets.planned_clips
              ? `${assets.clips} / ${assets.planned_clips}`
              : `${assets.clips}`,
            note: "Generated clips available",
            icon: Mic2,
            tone: "blue",
          },
          {
            title: "Production stages",
            value: steps.total
              ? `${steps.done} / ${steps.total}`
              : `${steps.done} recorded`,
            note: steps.total
              ? "Selected local run"
              : "A full run plan is not recorded",
            icon: Workflow,
            tone: "pink",
          },
          {
            title: "Production elapsed",
            value: duration(
              snapshot.production_clock?.elapsed_seconds ??
                snapshot.since_intake_seconds,
            ),
            note: snapshot.production_clock?.finished_at
              ? "Story intake to recorded delivery"
              : "Includes creative work and waiting",
            icon: Clock3,
            tone: "orange",
          },
        ].map((metric) => (
          <Card className="metric-card" key={metric.title}>
            <div className="flex items-center justify-between">
              <span className="metric-label">{metric.title}</span>
              <span className={`metric-icon tone-${metric.tone}`}>
                <metric.icon className="size-4" strokeWidth={1.7} />
              </span>
            </div>
            <strong>{metric.value}</strong>
            <p>{metric.note}</p>
          </Card>
        ))}
      </div>
      <span className="sr-only">
        Last recorded change {relative(snapshot.updated_at)}
      </span>
    </>
  );
}
