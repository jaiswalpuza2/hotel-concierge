"use client";

import { useCallback, useEffect, useRef, useState } from "react";

interface AudioPlayer {
  playing: boolean;
  /** 0..1 loudness of what is currently playing (for the speaking animation). */
  level: number;
  playBase64: (base64: string) => Promise<void>;
  stop: () => void;
}

function base64ToArrayBuffer(base64: string): ArrayBuffer {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes.buffer;
}

/** Plays server-synthesised speech with the Web Audio API and exposes a live level meter. */
export function useAudioPlayer(): AudioPlayer {
  const ctxRef = useRef<AudioContext | null>(null);
  const sourceRef = useRef<AudioBufferSourceNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const [playing, setPlaying] = useState(false);
  const [level, setLevel] = useState(0);

  const stopMeter = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    setLevel(0);
  }, []);

  const stop = useCallback(() => {
    try {
      sourceRef.current?.stop();
    } catch {
      /* already stopped */
    }
    sourceRef.current = null;
    setPlaying(false);
    stopMeter();
  }, [stopMeter]);

  const playBase64 = useCallback(
    async (base64: string) => {
      stop();
      const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      ctxRef.current ??= new AudioCtor();
      const ctx = ctxRef.current;
      if (ctx.state === "suspended") await ctx.resume();

      const buffer = await ctx.decodeAudioData(base64ToArrayBuffer(base64));
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(ctx.destination);
      sourceRef.current = source;

      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(Math.min(1, peak / 64));
        rafRef.current = requestAnimationFrame(tick);
      };
      source.onended = () => {
        setPlaying(false);
        stopMeter();
        sourceRef.current = null;
      };
      setPlaying(true);
      source.start();
      tick();
    },
    [stop, stopMeter],
  );

  useEffect(
    () => () => {
      stop();
      void ctxRef.current?.close();
    },
    [stop],
  );

  return { playing, level, playBase64, stop };
}
