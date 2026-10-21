import type { ReactNode } from "react";
import type { ThemeChoice } from "../lib/useTheme";

const THEME_OPTIONS: { value: ThemeChoice; label: string }[] = [
  { value: "system", label: "System" },
  { value: "light", label: "Light" },
  { value: "dark", label: "Dark" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h2 className="text-lg font-semibold">{title}</h2>
      <div className="space-y-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">{children}</div>
    </section>
  );
}

function Term({ term, children }: { term: string; children: ReactNode }) {
  return (
    <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-800">
      <dt className="font-mono text-sm font-semibold text-slate-800 dark:text-slate-200">{term}</dt>
      <dd className="mt-1 text-sm text-slate-600 dark:text-slate-400">{children}</dd>
    </div>
  );
}

export default function InfoPage({
  theme,
  onThemeChange,
  modelWeight,
}: {
  theme: ThemeChoice;
  onThemeChange: (theme: ThemeChoice) => void;
  modelWeight: number;
}) {
  return (
    <div className="space-y-8 rounded-xl border border-slate-200 bg-white p-5 dark:border-slate-800 dark:bg-slate-900 sm:p-6">
      <Section title="Appearance">
        <p>Defaults to your device's light/dark setting. Override it here if you'd rather it stay one way.</p>
        <div className="inline-flex overflow-hidden rounded-lg border border-slate-200 dark:border-slate-800">
          {THEME_OPTIONS.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => onThemeChange(value)}
              aria-pressed={theme === value}
              className={`px-3 py-1.5 text-sm font-medium transition-colors ${
                theme === value
                  ? "bg-slate-900 text-white dark:bg-white dark:text-slate-900"
                  : "bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      </Section>

      <Section title="How the projection works">
        <ol className="list-decimal space-y-1.5 pl-5">
          <li>
            <strong>Baseline.</strong> A recency-weighted average of the skater's shots on goal over his last 40
            games. Each game back counts a little less, and last season's games count for 60% of what they
            otherwise would, so early in the year the model leans on last season without letting it outweigh what's
            happening now.
          </li>
          <li>
            <strong>Opponent.</strong> The baseline is scaled by how many shots the opponent allows per game
            relative to league average &mdash; shrunk toward last season while the sample is small and capped at
            &plusmn;15%.
          </li>
          <li>
            <strong>Distribution.</strong> Shots are counts with streaky, overdispersed nights, so the over/under
            probability comes from a negative binomial distribution fit to the player's own game-to-game variance
            (Poisson when he's steadier than that).
          </li>
          <li>
            <strong>Blend with the market.</strong> A stat model alone is overconfident &mdash; books already know
            about line changes, power-play units and the opposing goalie. The final probability is{" "}
            {Math.round(modelWeight * 100)}% model and {Math.round((1 - modelWeight) * 100)}% the book's no-vig
            price.
          </li>
          <li>
            <strong>Edge</strong> is the blended probability minus the book's no-vig probability. Props are ranked
            by it, and every positive-edge pick is saved before puck drop and graded against the box score after.
          </li>
        </ol>
      </Section>

      <Section title="Glossary">
        <dl className="grid gap-2 sm:grid-cols-2">
          <Term term="Proj.">Projected shots on goal for this game, after the opponent adjustment.</Term>
          <Term term="Model %">The blended probability the recommended side wins, with the odds it implies.</Term>
          <Term term="Book %">The sportsbook's implied probability for that side with the vig removed.</Term>
          <Term term="Edge">Model % minus Book %. Positive means the model thinks the price is too long.</Term>
          <Term term="Opponent factor">
            Opponent's shots allowed per game vs. league average. 1.10x = allows 10% more shots than average.
          </Term>
          <Term term="Confidence">
            Low / Medium / High from sample size, recent results against this line, the matchup, ice-time trend
            and edge size. Open any prop to see which signals helped or hurt.
          </Term>
          <Term term="Void">
            A pick on a skater who didn't dress is voided, like a sportsbook would, rather than counted as a loss.
          </Term>
          <Term term="Units">Profit/loss betting 1 unit on every pick at the price it was recommended at.</Term>
        </dl>
      </Section>

      <Section title="Data sources">
        <p>
          Schedules, rosters, game logs and box scores come from the NHL's free public API. Odds come from{" "}
          <a className="underline" href="https://the-odds-api.com/" target="_blank" rel="noreferrer">
            The Odds API
          </a>{" "}
          (DraftKings and FanDuel). Everything refreshes automatically once a day before puck drop.
        </p>
      </Section>

      <Section title="Limitations">
        <ul className="list-disc space-y-1.5 pl-5">
          <li>Line combinations, power-play units and the opposing goalie aren't modeled directly.</li>
          <li>Late scratches after the daily refresh won't be reflected until the next run.</li>
          <li>
            This is a statistical tool, not betting advice. Sample sizes are small and no model captures everything
            a sportsbook prices in. Bet responsibly, or don't bet at all.
          </li>
        </ul>
      </Section>
    </div>
  );
}
