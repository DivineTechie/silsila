"use client";

// Read aloud: plays a pre-recorded clip of a SYNTHETIC voice reading approved text exactly as written.
// The API attaches a clip to a text only when the clip was recorded from that exact text (matched by
// SHA-256), so the voice cannot say anything that is not on screen. Nothing plays until the button is pressed,
// and only one clip plays at a time.

import { useEffect, useRef, useState } from "react";
import { API_URL } from "@/lib/api";
import { usePrefs } from "@/lib/prefs";
import type { AudioClip } from "@/lib/types";
import { cx } from "./ui";

let stopCurrent: (() => void) | null = null;

export function ListenButton({ clip, className }: { clip: AudioClip; className?: string }) {
  const { t } = usePrefs();
  const [playing, setPlaying] = useState(false);
  const [failed, setFailed] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null);

  useEffect(
    () => () => {
      audio.current?.pause();
    },
    [],
  );

  const stop = () => {
    audio.current?.pause();
    setPlaying(false);
  };

  const toggle = () => {
    if (playing) {
      stop();
      return;
    }
    stopCurrent?.();
    const a = new Audio(API_URL + clip.url);
    audio.current = a;
    stopCurrent = stop;
    setFailed(false);
    a.onended = () => setPlaying(false);
    a.onerror = () => {
      setPlaying(false);
      setFailed(true);
    };
    a.play().then(() => setPlaying(true), () => setFailed(true));
  };

  return (
    <span className={cx("inline-flex flex-wrap items-center gap-x-2 gap-y-1", className)}>
      <button
        type="button"
        onClick={toggle}
        aria-pressed={playing}
        className={cx(
          "inline-flex min-h-9 items-center gap-1.5 rounded-lg border px-2.5 text-xs font-medium",
          playing ? "border-accent bg-accent-soft text-ink" : "border-line-strong bg-surface text-ink hover:bg-surface-2",
        )}
      >
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" fill="currentColor" aria-hidden="true">
          {playing ? <rect x="3.5" y="3.5" width="9" height="9" rx="1" /> : <path d="M2 6v4h2.5L8 13V3L4.5 6H2zm8.5-1.2a4.5 4.5 0 0 1 0 6.4l-.9-.9a3.2 3.2 0 0 0 0-4.6l.9-.9z" />}
        </svg>
        {playing ? t("listen.stop") : t("listen.play")}
      </button>
      <span className="text-[0.7rem] text-muted">{t("listen.synthetic")}</span>
      {failed && <span role="status" className="text-[0.7rem] text-ink-2">{t("listen.failed")}</span>}
    </span>
  );
}
