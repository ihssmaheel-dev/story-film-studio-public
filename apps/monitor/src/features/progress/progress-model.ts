import type {
  Estimate,
  Job,
  JobState,
  MonitorSnapshot,
  ProductionEvent,
} from "@/types/monitor";

export interface ProgressStep {
  id: string;
  stage: string;
  title: string;
  state: JobState;
  statusLabel?: string;
  message: string;
  part: string | null;
  jobs: Job[];
  events: ProductionEvent[];
  startedAt: string | null;
  finishedAt: string | null;
  duration: number | null;
  completed: number | null;
  total: number | null;
  unit: string;
  percent: number | null;
  eta: Estimate;
  isCurrent: boolean;
}

const stages: Record<string, { title: string; rank: number }> = {
  intake: { title: "Story intake", rank: 0 },
  preflight: { title: "Production readiness", rank: 3 },
  story: { title: "Story review", rank: 5 },
  world: { title: "World & cast", rank: 10 },
  cast: { title: "Cast sheets", rank: 11 },
  shots: { title: "Shot planning", rank: 12 },
  images: { title: "Story images", rank: 15 },
  casting: { title: "Voice selection", rank: 20 },
  voice_setup: { title: "Voice setup", rank: 25 },
  audition: { title: "Voice audition", rank: 28 },
  narration: { title: "Voice performance", rank: 30 },
  alignment: { title: "Speech alignment", rank: 40 },
  timeline: { title: "Film timing", rank: 50 },
  sound: { title: "Sound preparation", rank: 60 },
  mix: { title: "Sound mix", rank: 70 },
  subtitles: { title: "Captions", rank: 80 },
  preview: { title: "Preview render", rank: 90 },
  review: { title: "Preview decision", rank: 100 },
  master: { title: "Master render", rank: 110 },
  qa: { title: "Quality checks", rank: 120 },
  delivery: { title: "Delivery", rank: 130 },
  coordinator: { title: "Production runner", rank: 140 },
  attention: { title: "Next action", rank: 145 },
};

export function stageOf(job: string): string {
  if (job.startsWith("render:"))
    return job.endsWith(":final") ? "master" : "preview";
  if (job.startsWith("run:")) return "coordinator";
  return job.split(":")[0];
}
export function isActive(state: JobState) {
  return state === "running" || state === "provider_wait";
}
export function isDone(state: JobState) {
  return state === "complete" || state === "cached";
}
export function needsAttention(state: JobState) {
  return ["failed", "interrupted", "stale", "waiting", "reported"].includes(
    state,
  );
}
export function displayState(state: JobState, connected: boolean): JobState {
  return !connected && isActive(state) ? "reported" : state;
}
const time = (value: string | null | undefined) =>
  value && Number.isFinite(Date.parse(value)) ? Date.parse(value) : 0;

export function buildProgressSteps(
  snapshot: MonitorSnapshot,
  partId: string,
): ProgressStep[] {
  const film = snapshot.media.find((part) => part.part === partId);
  const assets = snapshot.parts.find((part) => part.id === partId);
  const events = snapshot.events.filter(
    (event) => !event.part || event.part === partId,
  );
  const steps = new Map<string, ProgressStep>();
  function get(
    stage: string,
    part: string | null = partId,
    id = `${stage}:${part || "project"}`,
  ) {
    if (!steps.has(id))
      steps.set(id, {
        id,
        stage,
        title: stages[stage]?.title || stage.replaceAll("_", " "),
        state: "reported",
        message: "",
        part,
        jobs: [],
        events: [],
        startedAt: null,
        finishedAt: null,
        duration: null,
        completed: null,
        total: null,
        unit: "",
        percent: null,
        eta: { available: false, reason: "No estimate recorded" },
        isCurrent: false,
      });
    return steps.get(id)!;
  }

  for (const event of events) {
    const stage =
      event.kind === "intake"
        ? "intake"
        : event.kind === "voice_change"
          ? "casting"
          : stageOf(event.job);
    if (stage === "coordinator" || stage === "provider") continue;
    const step = get(
      stage,
      stage === "intake" || stage === "cast" ? null : event.part || partId,
    );
    step.events.push(event);
  }
  for (const job of snapshot.jobs) {
    if (job.part && job.part !== partId) continue;
    const stage = stageOf(job.id || "");
    if (!stage || (stage === "coordinator" && job.id !== snapshot.current.id))
      continue;
    const step = get(
      stage,
      job.part ||
        (stage === "provider" || stage === "coordinator" || stage === "cast"
          ? null
          : partId),
      stage === "provider" ? job.id : undefined,
    );
    step.jobs.push(job);
    if (stage === "provider") step.title = job.label;
  }
  for (const step of steps.values()) {
    step.events.sort((a, b) => time(b.at) - time(a.at));
    step.jobs.sort(
      (a, b) =>
        Number(isActive(b.state)) - Number(isActive(a.state)) ||
        time(b.heartbeat_at || b.finished_at || b.started_at) -
          time(a.heartbeat_at || a.finished_at || a.started_at),
    );
    const job = step.jobs[0],
      latest = step.events[0];
    if (job) {
      Object.assign(step, {
        state: job.state,
        message: job.message,
        startedAt: job.started_at || null,
        finishedAt: isDone(job.state) ? job.finished_at || null : null,
        duration: job.elapsed_seconds ?? null,
        completed: job.completed ?? null,
        total: job.total ?? null,
        unit: job.unit || "",
        percent: job.percent ?? null,
        eta: job.eta,
        isCurrent:
          job.id === snapshot.current.id ||
          (snapshot.current.state === "reported" &&
            job.label === snapshot.current.label),
      });
    } else if (latest) {
      step.state = ["complete", "cached", "failed", "interrupted"].includes(
        latest.kind,
      )
        ? latest.kind
        : ["intake", "voice_change", "decision", "delivery"].includes(
              latest.kind,
            )
          ? "complete"
          : latest.kind === "requested" || latest.kind === "started"
            ? "reported"
            : "reported";
      step.message = latest.detail || latest.message;
      step.finishedAt = isDone(step.state) ? latest.at : null;
      step.duration = latest.duration_seconds ?? null;
      step.isCurrent =
        snapshot.current.state === "reported" &&
        latest.label === snapshot.current.label;
    }
  }

  if (snapshot.cast?.total) {
    const step = get("cast", null);
    const cast = snapshot.cast;
    const generating = cast.characters.some(
      (item) => item.state === "provider_wait",
    );
    step.state =
      cast.ready === cast.total
        ? "complete"
        : cast.characters.some((item) =>
              ["failed", "unknown_result"].includes(item.state),
            )
          ? "failed"
          : generating
            ? "provider_wait"
            : "waiting";
    step.statusLabel =
      cast.ready === cast.total
        ? "Verified"
        : generating
          ? "Generating sheets"
          : "Cast preparation";
    step.completed = cast.ready;
    step.total = cast.total;
    step.unit = "characters";
    step.percent = (100 * cast.ready) / cast.total;
    step.message = `${cast.ready} of ${cast.total} characters have current inspected reference sheets. ${cast.pending_changes} change requests pending.`;
    step.isCurrent = generating;
  }
  if (assets && assets.images.total > 0) {
    const step = get("images");
    if (
      !step.jobs.some((job) => isActive(job.state)) &&
      !["failed", "interrupted", "stale"].includes(step.state)
    ) {
      step.state =
        assets.images.done >= assets.images.total ? "complete" : "waiting";
      step.statusLabel =
        step.state === "complete" ? "Available" : "Images pending";
    }
    Object.assign(step, {
      completed: assets.images.done,
      total: assets.images.total,
      unit: "images",
      percent: (100 * assets.images.done) / assets.images.total,
      message: `${assets.images.done} of ${assets.images.total} image files available. ${assets.images.reviewed} visual reviews recorded.`,
    });
  }
  if (film?.voices.length) {
    const step = get("casting");
    const selected = film.voices.filter(
      (voice) => voice.voice || voice.provider === "provided",
    ).length;
    step.state = selected === film.voices.length ? "complete" : "waiting";
    step.statusLabel =
      selected === film.voices.length ? "Configured" : "Selection pending";
    step.message = `${selected} of ${film.voices.length} speaking roles have a recorded voice selection.`;
    if (film.requires_speech && film.voices.some((voice) => !voice.current)) {
      const speech = get("narration");
      if (
        !isActive(speech.state) &&
        !["failed", "interrupted"].includes(speech.state)
      ) {
        speech.state = "stale";
        speech.statusLabel = "Update needed";
        speech.finishedAt = null;
        speech.message =
          "The selected voice has not been fully applied to the current speech.";
      }
    }
  }
  if (film?.preview.exists) {
    const preview = get("preview");
    if (
      !isActive(preview.state) &&
      !["failed", "interrupted"].includes(preview.state)
    ) {
      preview.state = film.preview.current
        ? preview.state === "cached"
          ? "cached"
          : "complete"
        : "stale";
      preview.statusLabel = film.preview.current
        ? preview.state === "cached"
          ? "Reused"
          : "Current"
        : "Update needed";
      preview.message = film.preview.current
        ? "The current preview matches its recorded inputs."
        : film.preview.reasons.join(". ");
      if (!film.preview.current) preview.finishedAt = null;
    }
    const review = get("review");
    review.state = film.preview.approved
      ? "complete"
      : film.preview.current
        ? "waiting"
        : "pending";
    review.statusLabel = film.preview.approved
      ? "Recorded"
      : film.preview.current
        ? "Your decision"
        : "Preview updating";
    review.message = film.preview.approved
      ? "A matching decision is recorded for this exact preview."
      : film.preview.current
        ? "Watch the current preview and give the production agent your actual decision."
        : "The preview must be updated before its next decision.";
    if (!film.preview.approved) review.finishedAt = null;
    review.isCurrent =
      snapshot.current.state === "waiting" &&
      film.preview.current &&
      !film.preview.approved;
  }
  if (film?.master_exists) {
    const step = get("master");
    if (
      !isActive(step.state) &&
      !["failed", "interrupted"].includes(step.state)
    ) {
      step.state = film.master_current
        ? step.state === "cached"
          ? "cached"
          : "complete"
        : "stale";
      step.statusLabel = film.master_current
        ? step.state === "cached"
          ? "Reused"
          : "Current"
        : "Update needed";
      step.message = film.master_current
        ? "A master file exists for the current presentation."
        : "An earlier master exists; the current presentation still needs a master.";
      if (!film.master_current) step.finishedAt = null;
    }
  }
  const delivery = steps.get(`delivery:${partId}`);
  if (delivery && film && (!film.master_current || !film.preview.approved)) {
    delivery.state = "stale";
    delivery.statusLabel = "Earlier delivery";
    delivery.finishedAt = null;
    delivery.message =
      "The earlier package is preserved. Current changes still need their own delivery.";
  }
  if (
    snapshot.attention.length &&
    ![...steps.values()].some(
      (step) => needsAttention(step.state) || isActive(step.state),
    )
  ) {
    const step = get("attention", null);
    step.state = snapshot.attention.some((item) => item.kind === "error")
      ? "failed"
      : "waiting";
    step.message = snapshot.attention.map((item) => item.message).join(" ");
    step.isCurrent = snapshot.current.state === "waiting";
  }
  return [...steps.values()].sort(
    (a, b) =>
      (stages[a.stage]?.rank ?? 85) - (stages[b.stage]?.rank ?? 85) ||
      a.id.localeCompare(b.id),
  );
}

export const STEP_SIZE = { width: 210, height: 108 };

export function stepLayout(index: number, columns: number) {
  const row = Math.floor(index / columns),
    slot = index % columns;
  return {
    x: (row % 2 ? columns - 1 - slot : slot) * (STEP_SIZE.width + 28),
    y: row * (STEP_SIZE.height + 28),
  };
}
