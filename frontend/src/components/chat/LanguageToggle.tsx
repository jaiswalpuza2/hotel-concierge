import type { Language } from "@/lib/types";

interface Props {
  value: Language;
  onChange: (lang: Language) => void;
}

const options: { value: Language; label: string; aria: string }[] = [
  { value: "en", label: "EN", aria: "English" },
  { value: "ne", label: "नेपाली", aria: "Nepali" },
];

export function LanguageToggle({ value, onChange }: Props) {
  return (
    <div role="radiogroup" aria-label="Language" className="inline-flex rounded-lg bg-white/15 p-0.5">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          aria-label={o.aria}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${
            value === o.value ? "bg-white text-brand" : "text-white/90 hover:bg-white/10"
          }`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}
