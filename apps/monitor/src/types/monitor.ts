export type JobState =
  | "running"
  | "complete"
  | "cached"
  | "failed"
  | "interrupted"
  | "pending"
  | "stale"
  | "reported"
  | "waiting"
  | "provider_wait"
  | "idle"
  | string;
export interface Estimate {
  available: boolean;
  low_seconds?: number;
  high_seconds?: number;
  reason?: string;
  basis?: string;
  scope?: string;
}
export interface Project {
  id: string;
  title: string;
  branch: string;
  workspace: string;
  path: string;
  state?: JobState;
  active?: string;
  attention_count?: number;
}
export interface Job {
  id?: string;
  label: string;
  state: JobState;
  message: string;
  part?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  heartbeat_at?: string | null;
  heartbeat_age_seconds?: number | null;
  progress_age_seconds?: number | null;
  elapsed_seconds?: number | null;
  completed?: number | null;
  total?: number | null;
  unit?: string;
  percent?: number | null;
  eta: Estimate;
  instrumented?: boolean;
}
export interface ProductionEvent {
  id: string;
  at: string;
  kind: string;
  job: string;
  label: string;
  message: string;
  detail?: string;
  part?: string | null;
  duration_seconds?: number | null;
  source?: string;
}
export interface TimedItem {
  id?: string;
  start: number;
  end: number;
  text?: string;
  description?: string;
  narration?: string;
  speaker?: string;
  voice?: string;
  role?: string;
  image_url?: string | null;
}
export interface Voice {
  speaker: string;
  name: string;
  provider: string;
  voice: string | null;
  model: string | null;
  rendered_voices: string[];
  clips: number;
  expected_clips: number | null;
  current: boolean;
}
export interface VoiceChange {
  id: string;
  at: string;
  speaker: string;
  from_voice: string | null;
  to_voice: string;
  reason: string;
  request: string;
  state: string;
}
export interface FilmPart {
  part: string;
  duration: number | null;
  shots: TimedItem[];
  speech: TimedItem[];
  captions: TimedItem[];
  sounds: TimedItem[];
  voices: Voice[];
  voice_changes: VoiceChange[];
  requires_speech: boolean;
  preview: {
    exists: boolean;
    current: boolean;
    approved: boolean;
    version: string;
    reasons: string[];
    url: string | null;
    review_state: string;
    at: number | null;
  };
  master_exists: boolean;
  master_current: boolean;
}
export interface MonitorSnapshot {
  cast?: CastWorkspace;
  cast_control?: { token: string; scope: string };
  project: Project;
  observed_at: string;
  updated_at: string | null;
  state: JobState;
  current: Job;
  jobs: Job[];
  steps: { done: number; total: number | null; scope: string };
  parts: Array<{
    id: string;
    title: string;
    images: { done: number; total: number; reviewed: number };
    voice: { done: number; total: number | null; applicable: boolean };
    preview: boolean;
    master: boolean;
    duration_seconds: number | null;
  }>;
  attention: Array<{ kind: string; actor: string; message: string }>;
  events: ProductionEvent[];
  media: FilmPart[];
  remaining_local: Estimate;
  run: {
    profile: string | null;
    status: string | null;
    started_at: string | null;
    finished_at: string | null;
  };
  since_intake_seconds: number | null;
  production_clock?: {
    started_at: string | null;
    finished_at: string | null;
    elapsed_seconds: number | null;
    scope: string;
  };
  assets: {
    images: number;
    shots: number;
    reviewed_images: number;
    clips: number;
    planned_clips: number | null;
    provider_requests: number;
    deliveries: number;
  };
  warnings: string[];
  read_only: boolean;
}
export type Section = "overview" | "progress" | "timeline" | "voices" | "cast";

export interface CastProfile {
  name: string;
  revision: string;
  style_id: string;
  style_revision: string;
  role: string;
  age_or_life_stage: string;
  design_type: string;
  personality: string;
  appearance: string;
  proportions: string;
  wardrobe: string;
  relative_scale: string;
  expression_system: string;
  identity_anchors: string[];
  views: string[];
  expressions: Record<string, string>;
  poses: Record<string, string>;
  state_variants?: Record<string, string>;
  reference_notes?: string;
}
export interface CastChange {
  id: string;
  character_id: string;
  request: string;
  source: string;
  at: string;
  status: string;
  base_version: string;
  applied_at?: string;
  revision?: string;
  affected_shots?: string[];
}
export interface CastCharacter {
  id: string;
  name: string;
  revision: string;
  style_id: string | null;
  style_revision: string | null;
  state: string;
  issues: string[];
  profile: CastProfile | null;
  legacy_document: string | null;
  design_version: string | null;
  images: Array<{
    path: string;
    sha256: string;
    url: string;
    previous: boolean;
  }>;
  review: {
    at: string;
    verdict: string;
    reviewer: string;
    notes: string;
    coverage: Record<string, Record<string, string>>;
  } | null;
  review_current: boolean;
  changes: CastChange[];
  linked_shots: string[];
}
export interface CastWorkspace {
  characters: CastCharacter[];
  total: number;
  ready: number;
  pending_changes: number;
  scope: string;
}
