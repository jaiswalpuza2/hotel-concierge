"use client";

import { useCallback, useState } from "react";
import { useSpeechRecognition } from "@/hooks/useSpeechRecognition";
import { useVoiceRecorder } from "@/hooks/useVoiceRecorder";
import { t } from "@/lib/i18n";
import type { Language } from "@/lib/types";

interface Props {
  language: Language;
  disabled: boolean;
  /** True when the server can transcribe audio (otherwise the browser's own recogniser is used). */
  serverStt: boolean;
  beginAudio: (mime: string) => boolean;
  sendAudioChunk: (chunk: Blob) => void;
  endAudio: () => void;
  /** Browser speech-recognition result (fallback path). */
  onTranscript: (text: string) => void;
}

export function VoiceButton({ language, disabled, serverStt, beginAudio, sendAudioChunk, endAudio, onTranscript }: Props) {
  const [problem, setProblem] = useState<string | null>(null);

  const recorder = useVoiceRecorder({ onChunk: sendAudioChunk, onStop: endAudio });
  const browser = useSpeechRecognition(language, onTranscript);

  const active = serverStt ? recorder.recording : browser.listening;
  const level = serverStt ? recorder.level : browser.listening ? 0.4 : 0;

  const toggle = useCallback(async () => {
    setProblem(null);
    if (serverStt) {
      if (recorder.recording) {
        recorder.stop();
        return;
      }
      const mime = await recorder.start();
      if (!mime) {
        setProblem(recorder.error === "denied" ? t(language, "micDenied") : t(language, "micUnsupported"));
        return;
      }
      beginAudio(mime);
      return;
    }
    if (browser.listening) {
      browser.stop();
      return;
    }
    if (!browser.supported || !browser.start()) setProblem(t(language, "micUnsupported"));
  }, [serverStt, recorder, browser, beginAudio, language]);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => void toggle()}
        disabled={disabled && !active}
        aria-pressed={active}
        aria-label={active ? t(language, "micStop") : t(language, "mic")}
        title={active ? t(language, "micStop") : t(language, "mic")}
        className={`relative flex h-11 w-11 items-center justify-center rounded-full transition-all duration-200 hover:scale-105 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100 ${
          active ? "bg-red-600 text-white" : "bg-stone-100 text-stone-700 hover:bg-stone-200"
        }`}
      >
        {active && (
          <>
            <span aria-hidden="true" className="ping-ring text-red-500/50" />
            <span
              aria-hidden="true"
              className="absolute inset-0 rounded-full bg-red-500/40"
              style={{ transform: `scale(${1 + level * 0.6})`, transition: "transform 80ms linear" }}
            />
          </>
        )}
        <svg viewBox="0 0 24 24" className="relative h-5 w-5" fill="currentColor" aria-hidden="true">
          <path d="M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.92V21h2v-3.08A7 7 0 0 0 19 11h-2Z" />
        </svg>
      </button>
      {problem && (
        <p role="alert" className="absolute bottom-14 right-0 w-64 rounded-lg bg-ink px-3 py-2 text-xs text-white shadow-lg">
          {problem}
        </p>
      )}
    </div>
  );
}
