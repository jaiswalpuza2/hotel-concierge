"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderError = "denied" | "unsupported" | "failed";

interface RecorderOptions {
  /** Called every ~250 ms with a chunk of encoded audio, so it can be streamed while recording. */
  onChunk: (chunk: Blob) => void;
  /** Called after the final chunk was delivered (recording fully finished). */
  onStop?: () => void;
}

interface VoiceRecorder {
  recording: boolean;
  /** 0..1 microphone loudness for the live meter. */
  level: number;
  error: RecorderError | null;
  mimeType: string;
  /** Starts recording; resolves to the recorder's MIME type, or null if it could not start. */
  start: () => Promise<string | null>;
  stop: () => void;
}

const PREFERRED_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4"];

function pickMimeType(): string {
  if (typeof MediaRecorder === "undefined") return "";
  return PREFERRED_TYPES.find((type) => MediaRecorder.isTypeSupported(type)) ?? "";
}

/** Records the microphone with MediaRecorder and measures loudness with the Web Audio API. */
export function useVoiceRecorder({ onChunk, onStop }: RecorderOptions): VoiceRecorder {
  const [recording, setRecording] = useState(false);
  const [level, setLevel] = useState(0);
  const [error, setError] = useState<RecorderError | null>(null);
  const [mimeType, setMimeType] = useState("");

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const rafRef = useRef<number | null>(null);
  const onChunkRef = useRef(onChunk);
  onChunkRef.current = onChunk;
  const onStopRef = useRef(onStop);
  onStopRef.current = onStop;

  const cleanup = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    void ctxRef.current?.close();
    ctxRef.current = null;
    recorderRef.current = null;
    setLevel(0);
    setRecording(false);
  }, []);

  const start = useCallback(async (): Promise<string | null> => {
    setError(null);
    if (typeof navigator === "undefined" || !navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === "undefined") {
      setError("unsupported");
      return null;
    }
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, channelCount: 1 },
      });
    } catch {
      setError("denied");
      return null;
    }
    try {
      streamRef.current = stream;
      const type = pickMimeType();
      const recorder = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
      const actualType = recorder.mimeType || type || "audio/webm";
      setMimeType(actualType);
      recorder.ondataavailable = (event: BlobEvent) => {
        if (event.data.size > 0) onChunkRef.current(event.data);
      };
      recorder.onstop = () => {
        cleanup();
        onStopRef.current?.();
      };
      recorderRef.current = recorder;

      const AudioCtor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
      const ctx = new AudioCtor();
      ctxRef.current = ctx;
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      ctx.createMediaStreamSource(stream).connect(analyser);
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteTimeDomainData(data);
        let peak = 0;
        for (const v of data) peak = Math.max(peak, Math.abs(v - 128));
        setLevel(Math.min(1, peak / 48));
        rafRef.current = requestAnimationFrame(tick);
      };

      recorder.start(250);
      setRecording(true);
      tick();
      return actualType;
    } catch {
      cleanup();
      setError("failed");
      return null;
    }
  }, [cleanup]);

  const stop = useCallback(() => {
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") recorder.stop();
    else cleanup();
  }, [cleanup]);

  useEffect(() => cleanup, [cleanup]);

  return { recording, level, error, mimeType, start, stop };
}
