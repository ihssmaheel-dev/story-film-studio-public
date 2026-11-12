import {
  AlertCircle,
  Check,
  CircleDashed,
  Clock3,
  LoaderCircle,
  Radio,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { stateLabels } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { JobState } from "@/types/monitor";

export function StatusBadge({
  state,
  label,
  className,
}: {
  state: JobState;
  label?: string;
  className?: string;
}) {
  const complete = ["complete", "cached", "approved"].includes(state);
  const running = state === "running";
  const error = ["failed", "interrupted"].includes(state);
  const waiting = ["waiting", "stale", "provider_wait", "reported"].includes(
    state,
  );
  const Icon = running
    ? LoaderCircle
    : complete
      ? Check
      : error
        ? AlertCircle
        : waiting
          ? Clock3
          : state === "idle"
            ? Radio
            : CircleDashed;
  return (
    <Badge
      variant="outline"
      className={cn(
        "status-badge",
        complete && "status-complete",
        running && "status-running",
        error && "status-error",
        waiting && "status-waiting",
        className,
      )}
    >
      <Icon className={cn("size-3", running && "motion-safe:animate-spin")} />
      {label || stateLabels[state] || state}
    </Badge>
  );
}
