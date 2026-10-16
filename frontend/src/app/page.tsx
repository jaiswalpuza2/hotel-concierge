import Link from "next/link";

const features = [
  {
    title: "Live rooms & prices",
    body: "Real availability, seasonal rates in NPR, and dates in both Gregorian and Bikram Sambat.",
    icon: "M3 7l9-4 9 4M3 7v10a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V7M9 21V12h6v9",
  },
  {
    title: "Book by chat or voice",
    body: "Reserve a room, a table, or a day trip — typed or spoken, guarded by explicit confirmation.",
    icon: "M12 14a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v5a3 3 0 0 0 3 3Zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-3.1A7 7 0 0 0 19 11h-2Z",
  },
  {
    title: "Answers with sources",
    body: "Every knowledge reply cites the hotel's own documents — menus, policies, festivals, attractions.",
    icon: "M12 6.5a4 4 0 0 0-4-2H4v13h4a4 4 0 0 1 4 2m0-13a4 4 0 0 1 4-2h4v13h-4a4 4 0 0 0-4 2m0-13v13",
  },
];

export default function HomePage() {
  return (
    <main className="relative min-h-screen overflow-hidden">
      {/* Decorative animated background */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 -z-10">
        <div className="anim-float absolute -top-24 -left-24 h-80 w-80 rounded-full bg-brand-soft blur-3xl" />
        <div className="anim-float absolute top-1/3 -right-28 h-96 w-96 rounded-full bg-gold-soft blur-3xl [animation-delay:1.6s]" />
        <div className="anim-float absolute -bottom-32 left-1/4 h-72 w-72 rounded-full bg-brand-soft blur-3xl [animation-delay:3.2s]" />
      </div>

      <section className="mx-auto flex min-h-screen max-w-4xl flex-col items-center justify-center px-6 py-16 text-center">
        <p className="anim-fade-up text-sm font-semibold uppercase tracking-widest text-gold">
          Himalayan Heritage Hotel
        </p>
        <h1 className="anim-fade-up d1 mt-4 max-w-2xl text-4xl font-bold leading-tight text-ink sm:text-6xl">
          Your AI concierge, in English and{" "}
          <span className="relative inline-block text-brand">
            नेपाली
            <span className="anim-grow-x d5 absolute -bottom-1 left-0 h-1 w-full rounded bg-gold" />
          </span>
        </h1>
        <p className="anim-fade-up d2 mt-6 max-w-xl text-lg text-stone-600">
          Ask about rooms and prices, book a stay, reserve a table or plan a day trip. Type or speak, whichever you
          prefer.
        </p>
        <div className="anim-fade-up d3 mt-10 flex flex-wrap justify-center gap-3">
          <Link
            href="/chat"
            className="group inline-flex items-center gap-2 rounded-xl bg-brand px-7 py-3.5 font-medium text-white shadow-lg shadow-brand/25 transition-all duration-200 hover:-translate-y-0.5 hover:bg-brand-dark hover:shadow-xl hover:shadow-brand/30 active:translate-y-0"
          >
            Start chatting
            <svg
              viewBox="0 0 24 24"
              className="h-4 w-4 transition-transform duration-200 group-hover:translate-x-1"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
              strokeLinecap="round"
              strokeLinejoin="round"
              aria-hidden="true"
            >
              <path d="M5 12h14m-6-6 6 6-6 6" />
            </svg>
          </Link>
          <Link
            href="/admin"
            className="inline-flex items-center rounded-xl border border-stone-300 bg-white/80 px-7 py-3.5 font-medium text-ink backdrop-blur transition-all duration-200 hover:-translate-y-0.5 hover:border-stone-400 hover:bg-white hover:shadow-md active:translate-y-0"
          >
            Staff dashboard
          </Link>
        </div>

        <div className="mt-16 grid w-full gap-4 text-left sm:grid-cols-3">
          {features.map((f, i) => (
            <div
              key={f.title}
              className={`anim-fade-up group rounded-2xl border border-stone-200 bg-white/80 p-5 shadow-sm backdrop-blur transition-all duration-200 hover:-translate-y-1 hover:border-gold/60 hover:shadow-lg ${
                i === 1 ? "d5" : i === 2 ? "d6" : "d4"
              }`}
            >
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand transition-transform duration-200 group-hover:scale-110">
                <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d={f.icon} />
                </svg>
              </span>
              <h2 className="mt-3 font-semibold text-ink">{f.title}</h2>
              <p className="mt-1 text-sm leading-relaxed text-stone-600">{f.body}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
