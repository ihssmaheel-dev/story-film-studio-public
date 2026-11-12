import { useRef, useState } from "react";
import { Field } from "@base-ui/react/field";
import {
  ArrowUpRight,
  Check,
  Clock3,
  FileImage,
  ImagePlus,
  LoaderCircle,
  PencilLine,
  Search,
  ShieldCheck,
  UserRound,
  UsersRound,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { SelectField } from "@/components/select-field";
import { timestamp } from "@/lib/format";
import { requestCastChange } from "@/lib/api";
import type { CastCharacter, MonitorSnapshot } from "@/types/monitor";

export const castStates: Record<string, string> = {
  ready: "Verified",
  profile_missing: "Profile needed",
  sheet_missing: "Sheet needed",
  awaiting_review: "Inspection needed",
  stale: "Update needed",
  failed: "Inspection failed",
  provider_wait: "Provider waiting",
  unknown_result: "Check provider result",
  changes_requested: "Change requested",
};
export function castLabel(state: string) {
  return castStates[state] || "Not recorded";
}

function CastState({
  character,
  connected,
}: {
  character: CastCharacter;
  connected: boolean;
}) {
  const active = character.state === "provider_wait" && connected;
  return (
    <Badge
      variant="outline"
      className={`cast-state cast-state-${character.state}`}
    >
      {active && <LoaderCircle className="size-3 motion-safe:animate-spin" />}
      {character.state === "ready" && <ShieldCheck className="size-3" />}
      {character.state === "provider_wait" && !connected
        ? "Last reported generation"
        : castLabel(character.state)}
    </Badge>
  );
}

function Requirements({
  title,
  entries,
  covered,
  current,
}: {
  title: string;
  entries: Record<string, string>;
  covered?: Record<string, string>;
  current: boolean;
}) {
  return (
    <section className="cast-detail-section">
      <h3>{title}</h3>
      <div className="cast-requirements">
        {Object.entries(entries).map(([name, detail]) => (
          <div key={name}>
            <span
              className={
                current && covered?.[name] ? "cast-covered" : "cast-uncovered"
              }
            >
              {current && covered?.[name] ? (
                <Check className="size-3.5" />
              ) : (
                <Clock3 className="size-3.5" />
              )}
            </span>
            <div>
              <strong>{name}</strong>
              {detail && <p>{detail}</p>}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

export function CastWorkspace({
  snapshot,
  connected,
  refresh,
}: {
  snapshot: MonitorSnapshot;
  connected: boolean;
  refresh: () => void;
}) {
  const [query, setQuery] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [fullImage, setFullImage] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [change, setChange] = useState("");
  const [baseVersion, setBaseVersion] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [saving, setSaving] = useState(false);
  const requestId = useRef<string | null>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const cast = snapshot.cast;
  const character =
    cast?.characters.find((item) => item.id === selected) || null;
  const rows = (cast?.characters || []).filter(
    (item) =>
      (filter === "all" ||
        (filter === "ready"
          ? item.state === "ready"
          : item.state !== "ready")) &&
      `${item.name} ${item.id} ${item.profile?.role || ""}`
        .toLowerCase()
        .includes(query.toLowerCase()),
  );
  function open(item: CastCharacter, trigger: HTMLElement) {
    returnFocus.current = trigger;
    setSelected(item.id);
    setEditing(false);
    setChange("");
    setError("");
    setMessage("");
    requestId.current = null;
  }
  function edit() {
    setEditing(true);
    setBaseVersion(character?.design_version || null);
    setChange("");
    setError("");
    setMessage("");
    requestId.current = crypto.randomUUID();
  }
  async function submit() {
    if (
      !character ||
      !baseVersion ||
      !snapshot.cast_control ||
      !requestId.current
    )
      return;
    setSaving(true);
    setError("");
    try {
      await requestCastChange(snapshot.cast_control.token, {
        project: snapshot.project.id,
        character_id: character.id,
        request: change.trim(),
        base_version: baseVersion,
        id: requestId.current,
      });
      setMessage(
        "Change recorded for the production agent. Your current sheet remains available while the revision is prepared.",
      );
      setEditing(false);
      refresh();
    } catch (reason) {
      setError(
        reason instanceof Error
          ? reason.message
          : "The change could not be recorded",
      );
    } finally {
      setSaving(false);
    }
  }
  const profile = character?.profile;
  const images = character?.images.filter((item) => !item.previous) || [];
  return (
    <div className="cast-workspace">
      <div className="cast-toolbar">
        <div className="cast-counts">
          <UsersRound className="size-4" />
          <strong>{cast?.total || 0} characters</strong>
          <span>{cast?.ready || 0} verified</span>
          {Boolean(cast?.pending_changes) && (
            <Badge variant="outline">
              {cast?.pending_changes} change requests
            </Badge>
          )}
        </div>
        <div className="cast-filters">
          <div className="cast-search">
            <Search className="size-3.5" />
            <Input
              aria-label="Search cast"
              placeholder="Search characters…"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
          <SelectField
            label="Cast status"
            value={filter}
            onChange={setFilter}
            options={[
              { value: "all", label: "All characters" },
              { value: "ready", label: "Verified sheets" },
              { value: "pending", label: "Needs attention" },
            ]}
          />
        </div>
      </div>
      <div className="cast-table-wrap">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Character</TableHead>
              <TableHead>Sheet coverage</TableHead>
              <TableHead>Linked shots</TableHead>
              <TableHead>Revision</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Details</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((item) => {
              const image = item.images.find((image) => !image.previous);
              const coverage = item.profile
                ? `${item.profile.views.length} views · ${Object.keys(item.profile.expressions).length} expressions · ${Object.keys(item.profile.poses).length} poses`
                : "Design brief not recorded";
              return (
                <TableRow key={item.id}>
                  <TableCell>
                    <Button
                      variant="ghost"
                      className="cast-character-button"
                      onClick={(event) => open(item, event.currentTarget)}
                    >
                      <span className="cast-thumbnail">
                        {image ? (
                          <img
                            src={image.url}
                            alt={`${item.name} cast reference`}
                            loading="lazy"
                          />
                        ) : (
                          <UserRound className="size-5" strokeWidth={1.4} />
                        )}
                      </span>
                      <span>
                        <strong>{item.name}</strong>
                        <small>{item.id}</small>
                      </span>
                    </Button>
                  </TableCell>
                  <TableCell>
                    <span className="cast-coverage-count">{coverage}</span>
                    <small className="cast-muted">
                      {item.images.filter((image) => !image.previous).length}{" "}
                      current reference files
                    </small>
                  </TableCell>
                  <TableCell>{item.linked_shots.length}</TableCell>
                  <TableCell>
                    <span className="font-mono text-xs">
                      {item.revision || "Unrecorded"}
                    </span>
                  </TableCell>
                  <TableCell>
                    <CastState character={item} connected={connected} />
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      variant="ghost"
                      size="sm"
                      aria-label={`Inspect ${item.name}`}
                      onClick={(event) => open(item, event.currentTarget)}
                    >
                      <ArrowUpRight className="size-4" />
                    </Button>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
      {!rows.length && (
        <div className="empty-inline">
          <UsersRound className="size-7" />
          <h3>
            {cast?.total ? "No matching characters" : "No cast registered yet"}
          </h3>
          <p>
            {cast?.total
              ? "Try another name or status."
              : "Character profiles and real reference sheets appear here as your production agent prepares them."}
          </p>
        </div>
      )}
      <p className="cast-footnote">
        <ShieldCheck className="size-3.5" />
        Verified means the current sheet has a recorded inspection for its exact
        design and image files.
      </p>
      <Dialog
        open={Boolean(character)}
        onOpenChange={(open) => {
          if (!open && !saving) setSelected(null);
        }}
        modal={false}
      >
        <DialogContent
          className="cast-drawer top-0 right-0 left-auto translate-x-0 translate-y-0"
          showOverlay={false}
          finalFocus={returnFocus}
        >
          <div className="cast-drawer-heading">
            <span className="cast-avatar">
              <UserRound className="size-5" />
            </span>
            <div>
              <DialogTitle>{character?.name || "Character"}</DialogTitle>
              <DialogDescription>
                {character?.id} · {character?.revision || "Draft design"}
              </DialogDescription>
            </div>
          </div>
          {character && (
            <div className="cast-drawer-body">
              <div className="cast-inspector-actions">
                <CastState character={character} connected={connected} />
                <Button
                  variant="outline"
                  size="sm"
                  onClick={edit}
                  disabled={
                    !connected ||
                    !snapshot.cast_control ||
                    !character.design_version ||
                    saving
                  }
                >
                  <PencilLine className="size-3.5" />
                  Request change
                </Button>
              </div>
              {message && (
                <p className="cast-notice" role="status">
                  {message}
                </p>
              )}
              {editing && (
                <section className="cast-change-form">
                  <Field.Root>
                    <Field.Label className="text-sm font-medium">
                      Character change request
                    </Field.Label>
                    <Field.Description className="mt-1 mb-3 text-xs leading-5 text-muted-foreground">
                      Describe the character, expression, pose or clothing
                      change. The agent will preserve earlier revisions and
                      check affected shots.
                    </Field.Description>
                    <Textarea
                      aria-label="Character change request"
                      value={change}
                      onValueChange={setChange}
                      maxLength={4000}
                      disabled={saving}
                      placeholder="For example: retain the face and outfit, make the silhouette older, and add a restrained grief expression."
                    />
                  </Field.Root>
                  {baseVersion !== character.design_version && (
                    <p className="cast-error">
                      This design changed while you were editing. Close this
                      form and review the current revision.
                    </p>
                  )}
                  {error && (
                    <p className="cast-error" role="alert">
                      {error}
                    </p>
                  )}
                  <div className="mt-3 flex justify-end gap-2">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditing(false)}
                      disabled={saving}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      onClick={submit}
                      disabled={
                        saving ||
                        !change.trim() ||
                        baseVersion !== character.design_version ||
                        !connected
                      }
                    >
                      {saving && (
                        <LoaderCircle className="size-3.5 motion-safe:animate-spin" />
                      )}
                      Record change request
                    </Button>
                  </div>
                </section>
              )}
              {images.length ? (
                <section className="cast-detail-section">
                  <h3>Current reference sheets</h3>
                  {images.map((image) => (
                    <Button
                      key={image.sha256}
                      variant="ghost"
                      className="cast-sheet-preview"
                      onClick={() => setFullImage(image.url)}
                    >
                      <img
                        src={image.url}
                        alt={`${character.name} current cast sheet`}
                      />
                      <span>
                        <FileImage className="size-3.5" />
                        View full sheet
                        <ArrowUpRight className="size-3.5" />
                      </span>
                    </Button>
                  ))}
                </section>
              ) : (
                <div className="cast-sheet-empty">
                  <ImagePlus className="size-6" strokeWidth={1.3} />
                  <strong>Cast sheet not linked</strong>
                  <p>
                    Style examples are not character identity sheets. The agent
                    needs to create and inspect this character’s reference.
                  </p>
                </div>
              )}
              {character.issues.length > 0 && (
                <section className="cast-issues">
                  <h3>Needs attention</h3>
                  {character.issues.map((issue) => (
                    <p key={issue}>{issue}</p>
                  ))}
                </section>
              )}
              {profile ? (
                <>
                  <section className="cast-detail-section">
                    <h3>Character design</h3>
                    <dl className="cast-facts">
                      {[
                        ["Role", profile.role],
                        ["Age / life stage", profile.age_or_life_stage],
                        ["Design type", profile.design_type],
                        ["Personality", profile.personality],
                        ["Appearance", profile.appearance],
                        ["Proportions", profile.proportions],
                        ["Wardrobe", profile.wardrobe],
                        ["Relative scale", profile.relative_scale],
                        ["Expression system", profile.expression_system],
                        [
                          "Visual style",
                          `${profile.style_id} / ${profile.style_revision}`,
                        ],
                      ].map(([name, value]) => (
                        <div key={name}>
                          <dt>{name}</dt>
                          <dd>{value}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                  <section className="cast-detail-section">
                    <h3>Identity anchors</h3>
                    <ul className="cast-anchor-list">
                      {profile.identity_anchors.map((anchor) => (
                        <li key={anchor}>{anchor}</li>
                      ))}
                    </ul>
                  </section>
                  <Requirements
                    title="Required identity views"
                    entries={Object.fromEntries(
                      profile.views.map((view) => [view, ""]),
                    )}
                    covered={character.review?.coverage.views}
                    current={character.review_current}
                  />
                  <Requirements
                    title="Expressions"
                    entries={profile.expressions}
                    covered={character.review?.coverage.expressions}
                    current={character.review_current}
                  />
                  <Requirements
                    title="Story poses"
                    entries={profile.poses}
                    covered={character.review?.coverage.poses}
                    current={character.review_current}
                  />
                  {Boolean(
                    Object.keys(profile.state_variants || {}).length,
                  ) && (
                    <Requirements
                      title="Event-driven variants"
                      entries={profile.state_variants || {}}
                      covered={character.review?.coverage.state_variants}
                      current={character.review_current}
                    />
                  )}
                </>
              ) : (
                <section className="cast-detail-section">
                  <h3>Existing character notes</h3>
                  <p className="cast-muted mb-3">
                    These notes have not been converted into a complete
                    structured cast profile.
                  </p>
                  <pre className="cast-legacy-notes">
                    {character.legacy_document ||
                      "No character notes recorded."}
                  </pre>
                </section>
              )}
              {character.review && (
                <section className="cast-detail-section">
                  <h3>
                    {character.review_current
                      ? "Current inspection"
                      : "Earlier inspection"}
                  </h3>
                  <p className="text-sm leading-6">{character.review.notes}</p>
                  <small className="cast-muted">
                    {character.review.reviewer} ·{" "}
                    {timestamp(character.review.at, true)}
                  </small>
                </section>
              )}
              <section className="cast-detail-section">
                <h3>Character revisions</h3>
                {character.changes.length ? (
                  [...character.changes].reverse().map((item) => (
                    <div className="cast-change-entry" key={item.id}>
                      <div>
                        <Badge variant="outline">
                          {item.status === "applied"
                            ? `${item.revision} applied`
                            : "Requested"}
                        </Badge>
                        <small>
                          {timestamp(item.applied_at || item.at, true)}
                        </small>
                      </div>
                      <p>{item.request}</p>
                      {item.affected_shots && (
                        <small>
                          {item.affected_shots.length} linked shots to inspect
                        </small>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="cast-muted">No character changes recorded.</p>
                )}
              </section>
              {character.images.some((image) => image.previous) && (
                <section className="cast-detail-section">
                  <h3>Preserved earlier references</h3>
                  <div className="cast-earlier-images">
                    {character.images
                      .filter((image) => image.previous)
                      .map((image) => (
                        <Button
                          variant="ghost"
                          key={image.sha256}
                          onClick={() => setFullImage(image.url)}
                          aria-label="View earlier character reference"
                        >
                          <img
                            src={image.url}
                            alt="Earlier character reference"
                          />
                        </Button>
                      ))}
                  </div>
                </section>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
      <Dialog
        open={Boolean(fullImage)}
        onOpenChange={(open) => {
          if (!open) setFullImage(null);
        }}
      >
        <DialogContent className="cast-lightbox max-w-[96vw] sm:max-w-[96vw]">
          <DialogTitle>Character reference sheet</DialogTitle>
          <DialogDescription>
            {character?.name} · Original registered image
          </DialogDescription>
          {fullImage && (
            <img
              src={fullImage}
              alt={`${character?.name || "Character"} full reference sheet`}
            />
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
