import { useState } from "react";
import { ArrowRight, AudioLines, Clock3, Mic2, UserRound } from "lucide-react";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { SectionPanel } from "@/components/section-panel";
import { SelectField } from "@/components/select-field";
import { StatusBadge } from "@/components/status-badge";
import { partLabel, timestamp } from "@/lib/format";
import type { FilmPart, MonitorSnapshot } from "@/types/monitor";

const providers: Record<string, string> = {
  kokoro: "Kokoro",
  chatterbox: "Chatterbox",
  elevenlabs: "ElevenLabs",
  inworld: "Inworld",
  cartesia: "Cartesia",
  provided: "Imported recording",
  "custom-http": "Custom gateway",
};

export function VoicesSummary({ part }: { part: FilmPart | null }) {
  const change = part
    ? [...part.voice_changes]
        .reverse()
        .find((item) => item.state !== "superseded")
    : null;
  return (
    <SectionPanel
      title="Cast & voices"
      description="The selected voices and their recorded speech."
    >
      <div className="voice-summary-list">
        {part?.voices.map((voice) => (
          <div key={voice.speaker} className="voice-summary-row">
            <span className="voice-avatar">
              <UserRound className="size-4" />
            </span>
            <div>
              <strong>{voice.name}</strong>
              <small>
                {voice.voice || "Not selected"}{" "}
                <span className="opacity-50">/</span>{" "}
                {providers[voice.provider] || voice.provider}
              </small>
            </div>
            <StatusBadge
              state={voice.current ? "complete" : "pending"}
              label={voice.current ? "Applied" : "Pending"}
            />
          </div>
        ))}
        {!part?.voices.length && (
          <p className="text-sm text-muted-foreground">
            Speaking roles appear when cast selections are recorded.
          </p>
        )}
      </div>
      {change && (
        <div className="voice-change-note">
          <span className="eyebrow">
            <AudioLines className="size-3" />
            LATEST VOICE CHANGE
          </span>
          <div className="my-2 flex items-center gap-2 font-mono text-xs">
            <span>{change.from_voice || "Unselected"}</span>
            <ArrowRight className="size-3" />
            <span>{change.to_voice}</span>
          </div>
          <p>{change.request || change.reason}</p>
          <small>
            {change.state === "review_ready"
              ? "Updated voice is in the current preview"
              : change.state === "speech_pending"
                ? "Speech update pending"
                : "Preview update pending"}
          </small>
        </div>
      )}
    </SectionPanel>
  );
}

export function VoicesPanel({ snapshot }: { snapshot: MonitorSnapshot }) {
  const [selected, setSelected] = useState(snapshot.media[0]?.part || "");
  const part =
    snapshot.media.find((item) => item.part === selected) || snapshot.media[0];
  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          Voice identity, generated performance and the complete recorded
          revision trail.
        </p>
        {part && (
          <SelectField
            label="Voice part"
            value={part.part}
            onChange={setSelected}
            options={snapshot.media.map((item) => ({
              value: item.part,
              label: partLabel(item.part),
            }))}
          />
        )}
      </div>
      <div className="voice-detail-grid">
        {part?.voices.map((voice) => {
          const latest = [...part.voice_changes]
            .reverse()
            .find(
              (change) =>
                change.speaker === voice.speaker &&
                change.to_voice === voice.voice,
            );
          return (
            <Card className="voice-detail-card" key={voice.speaker}>
              <div className="flex items-center justify-between">
                <span className="voice-detail-icon tone-purple">
                  <Mic2 className="size-5" />
                </span>
                <StatusBadge
                  state={voice.current ? "complete" : "pending"}
                  label={voice.current ? "Speech updated" : "Update pending"}
                />
              </div>
              <h2>{voice.name}</h2>
              <span className="font-mono text-xs text-muted-foreground">
                {voice.speaker}
              </span>
              <dl>
                <div>
                  <dt>Selected voice</dt>
                  <dd>{voice.voice || "Not selected"}</dd>
                </div>
                <div>
                  <dt>Provider</dt>
                  <dd>{providers[voice.provider] || voice.provider}</dd>
                </div>
                <div>
                  <dt>Model</dt>
                  <dd>{voice.model || "Not recorded"}</dd>
                </div>
                <div>
                  <dt>Generated clips</dt>
                  <dd>
                    {voice.clips}
                    {voice.expected_clips ? ` / ${voice.expected_clips}` : ""}
                  </dd>
                </div>
                <div>
                  <dt>Rendered voice</dt>
                  <dd>{voice.rendered_voices.join(", ") || "Not recorded"}</dd>
                </div>
              </dl>
              {latest?.reason && (
                <p className="voice-reason">{latest.reason}</p>
              )}
            </Card>
          );
        })}
      </div>
      <SectionPanel
        title="Voice revision history"
        description="Actual recorded selections and change requests."
        action={
          <Badge variant="outline">
            {part?.voice_changes.length || 0} revisions
          </Badge>
        }
      >
        <div className="voice-revision-list">
          {[...(part?.voice_changes || [])].reverse().map((change) => (
            <div className="voice-revision" key={change.id}>
              <span className="voice-avatar">
                <AudioLines className="size-4" />
              </span>
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap items-center gap-2">
                  <strong>
                    {change.speaker === "NARRATOR"
                      ? "Narrator"
                      : change.speaker}
                  </strong>
                  <Badge variant="outline">
                    {change.state === "superseded"
                      ? "Earlier selection"
                      : change.state === "review_ready"
                        ? "In current preview"
                        : "Update pending"}
                  </Badge>
                </div>
                <div className="my-2 flex items-center gap-2 font-mono text-xs">
                  <span>{change.from_voice || "Unselected"}</span>
                  <ArrowRight className="size-3" />
                  <span>{change.to_voice}</span>
                </div>
                <p>{change.request || change.reason}</p>
                <small className="mt-2 inline-flex items-center gap-1.5">
                  <Clock3 className="size-3" />
                  {timestamp(change.at, true)}{" "}
                  <span className="opacity-50">/</span> {change.id}
                </small>
              </div>
            </div>
          ))}
          {!part?.voice_changes.length && (
            <div className="empty-inline">
              <AudioLines className="size-6" />
              <h3>No voice revisions recorded</h3>
              <p>
                Voice selections and changes will appear here as they are made.
              </p>
            </div>
          )}
        </div>
      </SectionPanel>
    </div>
  );
}
