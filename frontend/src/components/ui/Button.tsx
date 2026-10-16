import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger";

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const styles: Record<Variant, string> = {
  primary: "bg-brand text-white hover:bg-brand-dark disabled:bg-stone-300",
  secondary: "border border-stone-300 bg-white text-ink hover:bg-stone-100 disabled:text-stone-400",
  ghost: "text-stone-600 hover:bg-stone-200/60 disabled:text-stone-300",
  danger: "bg-red-600 text-white hover:bg-red-700 disabled:bg-stone-300",
};

export function Button({ variant = "primary", className = "", type = "button", ...rest }: Props) {
  return (
    <button
      type={type}
      className={`inline-flex items-center justify-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-all duration-200 hover:-translate-y-px active:translate-y-0 active:scale-[.97] disabled:cursor-not-allowed disabled:hover:translate-y-0 disabled:active:scale-100 ${styles[variant]} ${className}`}
      {...rest}
    />
  );
}
