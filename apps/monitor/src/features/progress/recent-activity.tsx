import { ArrowUpRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionPanel } from "@/components/section-panel";
import { ProductionEventIcon } from "@/components/production-event-icon";
import { duration, timestamp } from "@/lib/format";
import type { MonitorSnapshot } from "@/types/monitor";

export function RecentActivity({
  snapshot,
  onOpen,
}: {
  snapshot: MonitorSnapshot;
  onOpen: () => void;
}) {
  return (
    <SectionPanel
      title="Recent activity"
      description="The latest changes in this production."
      action={
        <Button variant="ghost" size="sm" onClick={onOpen}>
          View all <ArrowUpRight className="size-3.5" />
        </Button>
      }
    >
      <div className="recent-events">
        {snapshot.events.slice(0, 5).map((event) => (
          <div className="recent-event" key={event.id}>
            <ProductionEventIcon event={event} />
            <div>
              <strong>{event.message}</strong>
              <small>
                {timestamp(event.at)}
                {event.kind === "cached"
                  ? " · Reused"
                  : event.duration_seconds != null
                    ? ` · ${duration(event.duration_seconds, true)}`
                    : ""}
              </small>
            </div>
          </div>
        ))}
        {!snapshot.events.length && (
          <p className="text-sm text-muted-foreground">
            No activity has been recorded yet.
          </p>
        )}
      </div>
    </SectionPanel>
  );
}
