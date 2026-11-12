import {
  AudioLines,
  Check,
  FileCheck2,
  Image,
  PackageCheck,
  Radio,
  Workflow,
  XCircle,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { ProductionEvent } from "@/types/monitor";

export function ProductionEventIcon({ event }: { event: ProductionEvent }) {
  const Icon =
    event.kind === "voice_change"
      ? AudioLines
      : event.kind === "delivery"
        ? PackageCheck
        : event.kind === "decision"
          ? FileCheck2
          : ["failed", "interrupted"].includes(event.kind)
            ? XCircle
            : event.kind === "started"
              ? Radio
              : event.job?.startsWith("images")
                ? Image
                : ["complete", "cached"].includes(event.kind)
                  ? Check
                  : Workflow;
  return (
    <span
      className={cn(
        "event-icon",
        event.kind === "voice_change" && "tone-purple",
        event.kind === "decision" && "tone-blue",
        event.kind === "delivery" && "tone-pink",
        event.kind === "failed" && "tone-error",
      )}
    >
      <Icon className="size-4" strokeWidth={1.7} />
    </span>
  );
}
