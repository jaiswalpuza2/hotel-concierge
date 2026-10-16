import type { ChatMessage, Language } from "@/lib/types";
import { t } from "@/lib/i18n";
import { CitationList } from "./CitationList";

interface Props {
  message: ChatMessage;
  language: Language;
}

export function MessageBubble({ message, language }: Props) {
  const isUser = message.role === "user";
  const isHuman = message.role === "human";
  const text = message.viaVoice && message.text === "" ? "…" : message.text;

  const bubble = isUser
    ? "rounded-br-sm bg-brand text-white"
    : isHuman
      ? "rounded-bl-sm border-2 border-gold bg-gold-soft text-ink"
      : "rounded-bl-sm border border-stone-200 bg-white text-ink";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-[15px] leading-relaxed shadow-sm sm:max-w-[75%] ${
          isUser ? "anim-slide-in-right" : "anim-slide-in-left"
        } ${bubble}`}
      >
        {isHuman && <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gold">{t(language, "humanLabel")}</p>}
        {message.viaVoice && isUser && <span aria-hidden="true" className="mr-1">🎙</span>}
        <p className="whitespace-pre-wrap break-words">
          {text}
          {message.streaming && <span className="caret-blink ml-0.5 inline-block h-4 w-1.5 translate-y-0.5 rounded-sm bg-stone-400" aria-hidden="true" />}
        </p>
        {message.citations && message.citations.length > 0 && !message.streaming && (
          <CitationList citations={message.citations} language={language} />
        )}
      </div>
    </div>
  );
}
