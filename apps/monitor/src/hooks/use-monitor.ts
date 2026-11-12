import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProjects, fetchSnapshot } from "@/lib/api";
import type { MonitorSnapshot, Project } from "@/types/monitor";

export function useMonitor() {
  const [projectId, setProjectId] = useState<string | null>(() =>
    new URLSearchParams(location.search).get("project"),
  );
  const [projects, setProjects] = useState<Project[]>([]);
  const [snapshot, setSnapshot] = useState<MonitorSnapshot | null>(null);
  const [connected, setConnected] = useState<boolean | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [revision, setRevision] = useState(0);
  const generation = useRef(0);
  const cache = useRef(new Map<string, MonitorSnapshot>());

  const selectProject = useCallback((id: string) => {
    setProjectId(id);
    setSnapshot(cache.current.get(id) || null);
    const url = new URL(location.href);
    url.searchParams.set("project", id);
    history.replaceState(null, "", url);
  }, []);
  const refresh = useCallback(() => setRevision((value) => value + 1), []);

  useEffect(() => {
    const currentGeneration = ++generation.current;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let active: AbortController | undefined;
    let busy = false;

    async function poll() {
      if (stopped || busy) return;
      clearTimeout(timer);
      busy = true;
      setRefreshing(true);
      active = new AbortController();
      const timeout = setTimeout(() => active?.abort(), 7000);
      try {
        const list = await fetchProjects(active.signal);
        if (stopped || generation.current !== currentGeneration) return;
        setProjects(list);
        const id = list.some((item) => item.id === projectId)
          ? projectId
          : list[0]?.id || null;
        if (id !== projectId) {
          setSnapshot(id ? cache.current.get(id) || null : null);
          setProjectId(id);
          setConnected(true);
          return;
        }
        if (id) {
          const value = await fetchSnapshot(id, active.signal);
          if (stopped || generation.current !== currentGeneration) return;
          cache.current.set(id, value);
          setSnapshot(value);
        } else setSnapshot(null);
        setConnected(true);
      } catch {
        if (!stopped && generation.current === currentGeneration)
          setConnected(false);
      } finally {
        clearTimeout(timeout);
        busy = false;
        if (!stopped) {
          setRefreshing(false);
          timer = setTimeout(poll, document.hidden ? 10000 : 2000);
        }
      }
    }

    const onVisible = () => {
      if (!document.hidden) void poll();
    };
    document.addEventListener("visibilitychange", onVisible);
    void poll();
    return () => {
      stopped = true;
      clearTimeout(timer);
      active?.abort();
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [projectId, revision]);

  return {
    projects,
    projectId,
    snapshot,
    connected,
    refreshing,
    selectProject,
    refresh,
  };
}
