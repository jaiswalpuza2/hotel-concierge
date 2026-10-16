"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Language } from "@/lib/types";

// Minimal typings: the Web Speech API is not part of lib.dom in TypeScript.
interface SpeechResultEvent {
  results: ArrayLike<ArrayLike<{ transcript: string }>>;
}
interface BrowserRecognition {
  lang: string;
  interimResults: boolean;
  maxAlternatives: number;
  onresult: ((event: SpeechResultEvent) => void) | null;
  onend: (() => void) | null;
  onerror: (() => void) | null;
  start: () => void;
  stop: () => void;
}
type RecognitionCtor = new () => BrowserRecognition;

function getCtor(): RecognitionCtor | null {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
}

/**
 * Fallback speech-to-text that runs in the browser (Chrome/Edge/Safari) when the server has
 * no speech provider configured. Supports Nepali (ne-NP) where the browser does.
 */
export function useSpeechRecognition(language: Language, onText: (text: string) => void) {
  const [listening, setListening] = useState(false);
  const recognitionRef = useRef<BrowserRecognition | null>(null);
  const onTextRef = useRef(onText);
  onTextRef.current = onText;
  const supported = getCtor() !== null;

  const start = useCallback(() => {
    const Ctor = getCtor();
    if (!Ctor) return false;
    const recognition = new Ctor();
    recognition.lang = language === "ne" ? "ne-NP" : "en-US";
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.onresult = (event) => {
      const first = event.results[0]?.[0];
      if (first?.transcript) onTextRef.current(first.transcript);
    };
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognitionRef.current = recognition;
    recognition.start();
    setListening(true);
    return true;
  }, [language]);

  const stop = useCallback(() => recognitionRef.current?.stop(), []);

  useEffect(() => () => recognitionRef.current?.stop(), []);

  return { supported, listening, start, stop };
}
