import type { Citation, Language } from "@/lib/types";
import { t } from "@/lib/i18n";

export function CitationList({ citations, language }: { citations: Citation[]; language: Language }) {
  return (
    <div className="mt-2 border-t border-stone-200 pt-2">
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-stone-500">{t(language, "sources")}</p>
      <ul className="flex flex-wrap gap-1.5">
        {citations.map((c, i) => (
          <li
            key={`${c.document_name}-${c.section ?? ""}-${i}`}
            className={`anim-scale-in cursor-default rounded-full bg-stone-100 px-2.5 py-0.5 text-xs text-stone-600 transition-colors duration-200 hover:bg-gold-soft hover:text-ink ${
              i === 1 ? "d1" : i === 2 ? "d2" : i >= 3 ? "d3" : ""
            }`}
            title={c.score !== undefined ? `relevance ${c.score}` : undefined}
          >
            {c.document_name}
            {c.section ? ` · ${c.section}` : ""}
            {c.page ? ` · p.${c.page}` : ""}
          </li>
        ))}
      </ul>
    </div>
  );
}
