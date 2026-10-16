"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent, KeyboardEvent } from "react";
import { useAudioPlayer } from "@/hooks/useAudioPlayer";
import { useChatSocket } from "@/hooks/useChatSocket";
import { api } from "@/lib/api";
import { t } from "@/lib/i18n";
import type { Capabilities, Language } from "@/lib/types";
import { LanguageToggle } from "./LanguageToggle";
import { MessageBubble } from "./MessageBubble";
import { TypingIndicator } from "./TypingIndicator";
import { VoiceButton } from "./VoiceButton";

const SESSION_KEY = "concierge_session_id";
const LANG_KEY = "concierge_language";
const SUGGESTIONS = ["s1", "s2", "s3", "s4"] as const;

function loadSessionId(): string {
  try {
    const existing = window.localStorage.getItem(SESSION_KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    window.localStorage.setItem(SESSION_KEY, fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

export function ChatWindow() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [language, setLanguage] = useState<Language>("en");

  useEffect(() => {
    setSessionId(loadSessionId());
    try {
      const saved = window.localStorage.getItem(LANG_KEY);
      if (saved === "en" || saved === "ne") setLanguage(saved);
    } catch {
      /* storage unavailable */
    }
  }, []);

  if (!sessionId) return null;
  return <ChatSession key={sessionId} sessionId={sessionId} language={language} onLanguage={setLanguage} onNewChat={() => {
    const fresh = crypto.randomUUID();
    try {
      window.localStorage.setItem(SESSION_KEY, fresh);
    } catch {
      /* storage unavailable */
    }
    setSessionId(fresh);
  }} />;
}

interface SessionProps {
  sessionId: string;
  language: Language;
  onLanguage: (lang: Language) => void;
  onNewChat: () => void;
}

function ChatSession({ sessionId, language, onLanguage, onNewChat }: SessionProps) {
  const [draft, setDraft] = useState("");
  const [speakReplies, setSpeakReplies] = useState(false);
  const [businessName, setBusinessName] = useState("Himalayan Heritage Hotel");
  const player = useAudioPlayer();
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const chat = useChatSocket({ sessionId, language, onAudio: (b64) => void player.playBase64(b64) });

  useEffect(() => {
    void api<Capabilities>("/api/v1/chat/capabilities", { auth: false })
      .then((c) => setBusinessName(c.business_name))
      .catch(() => undefined);
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [chat.messages, chat.stage]);

  const changeLanguage = useCallback(
    (lang: Language) => {
      onLanguage(lang);
      try {
        window.localStorage.setItem(LANG_KEY, lang);
      } catch {
        /* storage unavailable */
      }
    },
    [onLanguage],
  );

  const submit = useCallback(
    (text: string) => {
      if (chat.sendText(text, speakReplies && chat.capabilities.voice_output)) setDraft("");
    },
    [chat, speakReplies],
  );

  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    submit(draft);
  };
  const onKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      submit(draft);
    }
  };

  const connectionLabel = chat.connection === "open" ? t(language, "online") : chat.connection === "connecting" ? t(language, "connecting") : t(language, "offline");
  const empty = chat.messages.length === 0;
  const canSend = chat.connection === "open" && !chat.busy && draft.trim().length > 0;

  return (
    <div className="anim-fade-in mx-auto flex h-[100dvh] max-w-3xl flex-col bg-paper shadow-xl sm:my-0">
      <header className="flex items-center justify-between gap-3 bg-brand px-4 py-3 text-white">
        <div className="min-w-0">
          <h1 className="truncate text-lg font-semibold">{businessName}</h1>
          <p className="flex items-center gap-2 text-xs text-white/80">
            <span
              aria-hidden="true"
              className={`relative h-2 w-2 rounded-full ${chat.connection === "open" ? "bg-emerald-400" : "bg-amber-300"}`}
            >
              {chat.connection === "open" && <span className="ping-ring text-emerald-400" />}
            </span>
            {t(language, "title")} · {connectionLabel}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LanguageToggle value={language} onChange={changeLanguage} />
          <button
            type="button"
            onClick={onNewChat}
            className="rounded-md px-2 py-1 text-lg leading-none text-white/80 transition-all duration-200 hover:rotate-90 hover:bg-white/10"
            aria-label="Start a new conversation"
            title="New conversation"
          >
            +
          </button>
        </div>
      </header>

      {chat.handoffActive && (
        <div role="status" className="anim-slide-down border-b border-gold bg-gold-soft px-4 py-2 text-sm text-ink">
          {t(language, "humanBanner")}
        </div>
      )}

      <main className="scroll-thin flex-1 space-y-3 overflow-y-auto px-4 py-4" aria-live="polite" aria-label="Conversation">
        {empty && (
          <div className="anim-fade-up mx-auto mt-10 max-w-md text-center">
            <p className="text-2xl font-semibold text-brand">{t(language, "emptyTitle")}</p>
            <p className="mt-2 text-sm text-stone-600">{t(language, "emptyBody")}</p>
            <p className="mt-1 text-xs text-stone-500">{t(language, "subtitle")}</p>
            <div className="mt-6 flex flex-col gap-2">
              {SUGGESTIONS.map((key, i) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => submit(t(language, key))}
                  disabled={chat.connection !== "open"}
                  className={`anim-fade-up rounded-xl border border-stone-200 bg-white px-4 py-2.5 text-left text-sm text-stone-700 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-brand hover:text-brand hover:shadow-md disabled:opacity-50 ${
                    i === 1 ? "d1" : i === 2 ? "d2" : i === 3 ? "d3" : ""
                  }`}
                >
                  {t(language, key)}
                </button>
              ))}
            </div>
          </div>
        )}
        {chat.messages.map((m) => (
          <MessageBubble key={m.id} message={m} language={language} />
        ))}
        {chat.busy && !chat.messages.some((m) => m.streaming) && <TypingIndicator stage={chat.stage} language={language} />}
        {chat.error && (
          <p role="alert" className="anim-shake mx-auto max-w-md rounded-lg bg-red-50 px-3 py-2 text-center text-sm text-red-700">
            {chat.error}
          </p>
        )}
        <div ref={bottomRef} />
      </main>

      <form onSubmit={onSubmit} className="border-t border-stone-200 bg-white px-3 py-3">
        {chat.capabilities.voice_output && (
          <label className="mb-2 flex items-center gap-2 text-xs text-stone-600">
            <input
              type="checkbox"
              checked={speakReplies}
              onChange={(e) => {
                setSpeakReplies(e.target.checked);
                if (!e.target.checked) player.stop();
              }}
              className="h-4 w-4 accent-brand"
            />
            {t(language, "voiceReplies")}
            {player.playing && (
              <span aria-hidden="true" className="ml-1 inline-flex h-3 items-end gap-0.5">
                {[0.4, 0.8, 0.55].map((f, i) => (
                  <span key={i} className="eq-bar w-1 rounded bg-brand" style={{ height: `${Math.max(3, (f + player.level) * 8)}px`, animationDelay: `${i * 0.14}s` }} />
                ))}
              </span>
            )}
          </label>
        )}
        <div className="flex items-end gap-2">
          <textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            maxLength={1000}
            placeholder={t(language, "placeholder")}
            aria-label={t(language, "placeholder")}
            className="max-h-32 min-h-[44px] flex-1 resize-none rounded-2xl border border-stone-300 px-4 py-2.5 text-[15px] transition-colors duration-200 focus:border-brand focus:ring-2 focus:ring-brand/15"
          />
          <VoiceButton
            language={language}
            disabled={chat.connection !== "open" || chat.busy}
            serverStt={chat.capabilities.voice_input}
            beginAudio={(mime) => chat.beginAudio(mime, speakReplies && chat.capabilities.voice_output)}
            sendAudioChunk={chat.sendAudioChunk}
            endAudio={chat.endAudio}
            onTranscript={submit}
          />
          <button
            type="submit"
            disabled={!canSend}
            className="h-11 rounded-full bg-brand px-5 text-sm font-medium text-white transition-all duration-200 hover:scale-105 hover:bg-brand-dark active:scale-95 disabled:scale-100 disabled:bg-stone-300"
          >
            {t(language, "send")}
          </button>
        </div>
      </form>
    </div>
  );
}
