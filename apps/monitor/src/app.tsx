import { lazy, Suspense, useEffect, useState } from "react";
import {
  ArrowUpRight,
  Clapperboard,
  Eye,
  Info,
  Rows3,
  UsersRound,
} from "lucide-react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { AppShell } from "@/components/app-shell";
import { useMonitor } from "@/hooks/use-monitor";
import { CurrentOperation } from "@/features/production/current-operation";
import { StageTable } from "@/features/production/stage-table";
import { RecentActivity } from "@/features/progress/recent-activity";
import { VoicesPanel } from "@/features/voices/voices-panel";
import { FilmSummary } from "@/features/media/film-summary";
import { VoicesSummary } from "@/features/voices/voices-panel";
import { timestamp } from "@/lib/format";
import type { Section } from "@/types/monitor";

const sectionInfo = {
  overview: {
    eyebrow: "PRODUCTION OVERVIEW",
    subtitle: "Live tasks, measured timings and production records.",
  },
  progress: {
    eyebrow: "PRODUCTION PROGRESS",
    subtitle: "Follow each recorded step, live activity and the next action.",
  },
  timeline: {
    eyebrow: "FILM TIMELINE",
    subtitle:
      "Explore the measured shots, performances, captions and sound in your film.",
  },
  voices: {
    eyebrow: "CAST & VOICES",
    subtitle:
      "Voice selections, generated performance and the changes along the way.",
  },
  cast: {
    eyebrow: "VISUAL CAST",
    subtitle:
      "Character identity, reference sheets, expression coverage and design revisions.",
  },
};
const CastWorkspace = lazy(() =>
  import("@/features/cast/cast-workspace").then((module) => ({
    default: module.CastWorkspace,
  })),
);
const ProductionProgress = lazy(() =>
  import("@/features/progress/production-progress").then((module) => ({
    default: module.ProductionProgress,
  })),
);
const MediaWorkspace = lazy(() =>
  import("@/features/media/media-workspace").then((module) => ({
    default: module.MediaWorkspace,
  })),
);
function sectionFromUrl(): Section {
  const hash = location.hash.slice(1);
  if (hash === "film-timeline") return "timeline";
  if (hash === "activity-panel" || hash === "history") return "progress";
  return hash in sectionInfo ? (hash as Section) : "overview";
}

export default function App() {
  const monitor = useMonitor();
  const [section, setSection] = useState<Section>(sectionFromUrl);
  const { snapshot } = monitor;
  useEffect(() => {
    function onLocation() {
      setSection(sectionFromUrl());
    }
    addEventListener("popstate", onLocation);
    addEventListener("hashchange", onLocation);
    return () => {
      removeEventListener("popstate", onLocation);
      removeEventListener("hashchange", onLocation);
    };
  }, []);
  useEffect(() => {
    document.title = snapshot
      ? `${snapshot.project.title} — Studio Monitor`
      : "Studio Monitor — Story Film Studio";
  }, [snapshot?.project.title]);
  function navigate(value: Section) {
    setSection(value);
    const url = new URL(location.href);
    url.hash = value;
    history.pushState(null, "", url);
    scrollTo({ top: 0, behavior: "instant" });
  }
  return (
    <TooltipProvider delay={250}>
      <AppShell
        projects={monitor.projects}
        selected={monitor.projectId}
        project={snapshot?.project}
        section={section}
        navigate={navigate}
        selectProject={monitor.selectProject}
        connected={monitor.connected}
        refreshing={monitor.refreshing}
        refresh={monitor.refresh}
      >
        {!snapshot ? (
          monitor.connected === true && !monitor.projects.length ? (
            <div className="welcome-state">
              <Clapperboard className="size-10" strokeWidth={1.2} />
              <span className="eyebrow">STORY FILM STUDIO</span>
              <h1>Your production, in focus.</h1>
              <p>
                Your initialized stories will appear here. The monitor follows
                real production records as they are created.
              </p>
            </div>
          ) : (
            <div className="loading-state" aria-label="Loading production">
              <Skeleton className="mb-4 h-5 w-32" />
              <Skeleton className="h-10 w-72" />
              <Skeleton className="mt-8 h-40 w-full" />
              <div className="mt-5 grid grid-cols-2 gap-4 lg:grid-cols-4">
                {[0, 1, 2, 3].map((value) => (
                  <Skeleton className="h-32" key={value} />
                ))}
              </div>
            </div>
          )
        ) : (
          <>
            <div className="page-heading">
              <div>
                <span className="eyebrow">{sectionInfo[section].eyebrow}</span>
                <h1>
                  {section === "overview"
                    ? snapshot.project.title
                    : section === "progress"
                      ? "Production Progress"
                      : section === "timeline"
                        ? "Film timeline"
                        : section === "cast"
                          ? "Cast sheets"
                          : "Voices"}
                </h1>
                <p>{sectionInfo[section].subtitle}</p>
              </div>
              <div className="page-actions">
                {section !== "timeline" && (
                  <Button
                    variant="outline"
                    onClick={() => navigate("timeline")}
                  >
                    <Rows3 className="size-3.5" />
                    Film timeline
                  </Button>
                )}
                {section === "overview" &&
                  snapshot.media.some((part) => part.preview.exists) && (
                    <Button onClick={() => navigate("timeline")}>
                      <Eye className="size-3.5" />
                      Watch preview
                      <ArrowUpRight className="size-3.5" />
                    </Button>
                  )}
              </div>
            </div>
            {section === "overview" && (
              <CurrentOperation snapshot={snapshot} navigate={navigate} />
            )}
            {section === "timeline" && (
              <div id="film-workspace">
                <Suspense fallback={<Skeleton className="h-96 w-full" />}>
                  <MediaWorkspace
                    key={snapshot.project.id}
                    snapshot={snapshot}
                    expanded={section === "timeline"}
                  />
                </Suspense>
              </div>
            )}
            {section === "progress" && (
              <Suspense fallback={<Skeleton className="h-96 w-full" />}>
                <ProductionProgress
                  connected={monitor.connected === true}
                  key={snapshot.project.id}
                  snapshot={snapshot}
                />
              </Suspense>
            )}
            {section === "voices" && (
              <VoicesPanel key={snapshot.project.id} snapshot={snapshot} />
            )}
            {section === "cast" && (
              <Suspense fallback={<Skeleton className="h-96 w-full" />}>
                <CastWorkspace
                  key={snapshot.project.id}
                  snapshot={snapshot}
                  connected={monitor.connected === true}
                  refresh={monitor.refresh}
                />
              </Suspense>
            )}
            {section === "overview" && (
              <>
                {Boolean(snapshot.cast?.total) && (
                  <Button
                    variant="outline"
                    className="cast-overview-link"
                    onClick={() => navigate("cast")}
                  >
                    <UsersRound className="size-4" />
                    <strong>Cast sheets</strong>
                    <span>
                      {snapshot.cast?.ready} / {snapshot.cast?.total} verified
                    </span>
                    {Boolean(snapshot.cast?.pending_changes) && (
                      <span>
                        {snapshot.cast?.pending_changes} changes requested
                      </span>
                    )}
                    <ArrowUpRight className="ml-auto size-4" />
                  </Button>
                )}
                <StageTable
                  snapshot={snapshot}
                  onProgress={() => navigate("progress")}
                />
                <div className="overview-summary-grid">
                  <FilmSummary
                    part={snapshot.media[0] || null}
                    open={() => navigate("timeline")}
                  />
                  <RecentActivity
                    snapshot={snapshot}
                    onOpen={() => navigate("progress")}
                  />
                  <VoicesSummary part={snapshot.media[0] || null} />
                </div>
              </>
            )}
            {snapshot.warnings.length > 0 && (
              <div className="record-notes">
                <Info className="size-4" />
                <div>
                  {snapshot.warnings.map((warning) => (
                    <p key={warning}>{warning}</p>
                  ))}
                </div>
              </div>
            )}
            <footer className="monitor-footer">
              <span>
                <span className="live-dot" />
                Snapshot {timestamp(snapshot.observed_at)}{" "}
                <span className="footer-separator">/</span> Updated every 2
                seconds
              </span>
              <span>
                Local production monitor{" "}
                <span className="footer-separator">/</span> Character changes go
                to your production agent
              </span>
            </footer>
          </>
        )}
      </AppShell>
    </TooltipProvider>
  );
}
