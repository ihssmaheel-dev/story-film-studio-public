import { useEffect, useRef, useState } from "react";
import type { FilmPart } from "@/types/monitor";

export function usePreview(latest: FilmPart) {
  const video = useRef<HTMLVideoElement>(null);
  const container = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState<FilmPart | null>(
    latest.preview.exists ? latest : null,
  );
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [mediaDuration, setMediaDuration] = useState(0);
  const [volume, setVolume] = useState(0.8);
  const [muted, setMuted] = useState(false);
  const [speed, setSpeed] = useState("1");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!loaded && latest.preview.exists) setLoaded(latest);
  }, [latest, loaded]);

  function loadLatest() {
    video.current?.pause();
    setLoaded(latest);
    setTime(0);
    setError(null);
  }
  async function togglePlay() {
    const target = video.current;
    if (!target || !loaded?.preview.exists) return;
    if (!target.paused) target.pause();
    else {
      try {
        await target.play();
      } catch {
        setError(
          "Playback is unavailable. Load the latest preview or refresh the production records.",
        );
      }
    }
  }
  function seek(value: number) {
    if (!loaded?.preview.current || !video.current || !Number.isFinite(value))
      return;
    const end = Number.isFinite(video.current.duration)
      ? video.current.duration
      : loaded.duration || 0;
    video.current.currentTime = Math.max(0, Math.min(value, end));
    setTime(video.current.currentTime);
  }
  function changeVolume(value: number) {
    setVolume(value);
    if (video.current) video.current.volume = value;
    if (value > 0) {
      setMuted(false);
      if (video.current) video.current.muted = false;
    }
  }
  function toggleMute() {
    setMuted((value) => !value);
    if (video.current) video.current.muted = !muted;
  }
  function changeSpeed(value: string) {
    setSpeed(value);
    if (video.current) video.current.playbackRate = Number(value);
  }
  const events = {
    onTimeUpdate: () => setTime(video.current?.currentTime || 0),
    onLoadedMetadata: () => {
      setMediaDuration(video.current?.duration || 0);
      if (video.current) {
        video.current.volume = volume;
        video.current.muted = muted;
        video.current.playbackRate = Number(speed);
      }
    },
    onPlay: () => setPlaying(true),
    onPause: () => setPlaying(false),
    onEnded: () => setPlaying(false),
    onCanPlay: () => setError(null),
    onError: () => {
      if (loaded?.preview.url)
        setError(
          "This preview revision has changed or is unavailable. Load the latest version when it appears.",
        );
    },
  };
  return {
    video,
    container,
    loaded,
    playing,
    time,
    mediaDuration,
    volume,
    muted,
    speed,
    error,
    events,
    newVersion: Boolean(
      loaded &&
      loaded.preview.url !== latest.preview.url &&
      latest.preview.exists,
    ),
    loadLatest,
    togglePlay,
    seek,
    changeVolume,
    toggleMute,
    changeSpeed,
    fullscreen: () => {
      void container.current
        ?.requestFullscreen()
        .catch(() => setError("Full screen is unavailable in this browser."));
    },
  };
}
export type PreviewController = ReturnType<typeof usePreview>;
