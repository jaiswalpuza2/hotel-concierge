import type { Language } from "@/lib/types";
import { t } from "@/lib/i18n";

export function TypingIndicator({ stage, language }: { stage: string | null; language: Language }) {
  const label = stage ? t(language, `stage_${stage}`) : t(language, "stage_thinking");
  return (
    <div className="flex justify-start" role="status" aria-live="polite">
      <div className="anim-fade-up flex items-center gap-3 rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-4 py-2.5 text-sm text-stone-600 shadow-sm">
        <span className="flex gap-1" aria-hidden="true">
          {[0, 1, 2].map((i) => (
            <span key={i} className="h-1.5 w-1.5 animate-dot rounded-full bg-brand" style={{ animationDelay: `${i * 0.18}s` }} />
          ))}
        </span>
        {label}
      </div>
    </div>
  );
}
