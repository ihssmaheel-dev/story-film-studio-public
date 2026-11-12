import { Clock3, FileText, LoaderCircle } from "lucide-react";
import type { RefObject } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import { StatusBadge } from "@/components/status-badge";
import { duration, partLabel, timestamp } from "@/lib/format";
import type { MonitorSnapshot } from "@/types/monitor";
import { displayState, isActive, type ProgressStep } from "./progress-model";
import { StepIcon } from "./progress-step-node";

export function ProgressStepDrawer({
  step,
  snapshot,
  connected,
  close,
  returnFocus,
}: {
  step: ProgressStep | null;
  snapshot: MonitorSnapshot;
  connected: boolean;
  close: () => void;
  returnFocus: RefObject<HTMLElement | null>;
}) {
  const state = step ? displayState(step.state, connected) : "idle";
  return (
    <Dialog
      open={Boolean(step)}
      onOpenChange={(open) => {
        if (!open) close();
      }}
      modal={false}
    >
      <DialogContent
        className="progress-drawer top-0 right-0 left-auto translate-x-0 translate-y-0"
        showOverlay={false}
        finalFocus={returnFocus}
      >
        <div className="progress-drawer-header">
          <span className="progress-drawer-icon">
            {step && <StepIcon stage={step.stage} />}
          </span>
          <div>
            <DialogTitle>{step?.title || "Step details"}</DialogTitle>
            <DialogDescription>
              {step?.part ? partLabel(step.part) : "Project-wide progress"} ·
              Live recorded details
            </DialogDescription>
          </div>
        </div>
        {step && (
          <div className="progress-drawer-body">
            <div className="progress-drawer-state">
              <StatusBadge
                state={state}
                label={
                  !connected && isActive(step.state)
                    ? "Last reported activity"
                    : step.statusLabel
                }
              />
              {step.isCurrent && <Badge variant="outline">Current step</Badge>}
            </div>
            <p className="progress-step-description">
              {step.message || "No additional message was recorded."}
            </p>
            {step.stage === "cast" && (
              <a
                className="text-sm font-medium underline underline-offset-4"
                href="#cast"
              >
                Open cast sheets and character revisions
              </a>
            )}
            {isActive(state) && (
              <div className="progress-drawer-live">
                <LoaderCircle className="size-4 motion-safe:animate-spin" />
                <span>
                  {state === "provider_wait"
                    ? "Request submitted. Waiting for the provider."
                    : "This step is currently running."}
                </span>
              </div>
            )}
            {step.percent != null && (
              <div className="progress-drawer-measure">
                <div>
                  <span>
                    {step.completed ?? 0} / {step.total} {step.unit}
                  </span>
                  <strong>{Math.round(step.percent)}%</strong>
                </div>
                <Progress
                  value={step.percent}
                  aria-label="Selected step measured progress"
                />
              </div>
            )}
            <dl className="progress-facts">
              <div>
                <dt>Started</dt>
                <dd>{timestamp(step.startedAt, true)}</dd>
              </div>
              <div>
                <dt>Completed</dt>
                <dd>{timestamp(step.finishedAt, true)}</dd>
              </div>
              <div>
                <dt>{isActive(state) ? "Elapsed" : "Measured duration"}</dt>
                <dd>{duration(step.duration, true)}</dd>
              </div>
              <div>
                <dt>Time remaining</dt>
                <dd>
                  {isActive(state) && step.eta.available
                    ? `${duration(step.eta.low_seconds)} – ${duration(step.eta.high_seconds)}`
                    : "Not estimated"}
                </dd>
              </div>
            </dl>
            {isActive(state) && (
              <p className="progress-estimate-note">
                {step.eta.available
                  ? step.eta.basis
                  : step.eta.reason ||
                    "The current task has not reported an estimate."}
              </p>
            )}
            {step.jobs.length > 0 && (
              <section className="progress-record-section">
                <h3>
                  Task records <span>{step.jobs.length}</span>
                </h3>
                {step.jobs.map((job, index) => (
                  <div className="progress-job-record" key={job.id || index}>
                    <div>
                      <strong>{job.label}</strong>
                      <StatusBadge state={displayState(job.state, connected)} />
                    </div>
                    <p>{job.message}</p>
                    <code>{job.id}</code>
                    {job.heartbeat_at && (
                      <small>
                        Heartbeat {timestamp(job.heartbeat_at, true)}
                      </small>
                    )}
                  </div>
                ))}
              </section>
            )}
            <section className="progress-record-section">
              <h3>
                Recorded activity <span>{step.events.length}</span>
              </h3>
              {step.events.map((event) => (
                <div className="progress-evidence-event" key={event.id}>
                  <span className="progress-evidence-dot" />
                  <div>
                    <strong>{event.message}</strong>
                    <small>
                      <Clock3 className="size-3" />
                      {timestamp(event.at, true)}
                      {event.duration_seconds != null
                        ? ` · ${duration(event.duration_seconds, true)}`
                        : ""}
                    </small>
                    {event.detail && <p>{event.detail}</p>}
                    <span className="progress-evidence-source">
                      {event.source?.replaceAll("-", " ") ||
                        "Production record"}
                    </span>
                  </div>
                </div>
              ))}
              {!step.events.length && (
                <div className="progress-empty-evidence">
                  <FileText className="size-4" />
                  <p>
                    No timestamped activity was recorded for this step. Its
                    current task or asset record is shown above.
                  </p>
                </div>
              )}
            </section>
            {snapshot.attention.length > 0 && (
              <section className="progress-record-section">
                <h3>
                  Project actions <span>{snapshot.attention.length}</span>
                </h3>
                {snapshot.attention.map((item, index) => (
                  <div className="progress-project-action" key={index}>
                    <strong>
                      {item.actor === "user"
                        ? "Your decision"
                        : "Studio action"}
                    </strong>
                    <p>{item.message}</p>
                  </div>
                ))}
              </section>
            )}
            <div className="progress-drawer-footnote">
              Updated from production records. This view never starts tasks or
              records an approval.
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
