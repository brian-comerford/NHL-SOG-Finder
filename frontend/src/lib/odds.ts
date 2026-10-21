import type { Prop, Side } from "./types";

export function sidePrice(prop: Prop, side: Side): number | null {
  return side === "over" ? prop.price_over : prop.price_under;
}

export function sideBook(prop: Prop, side: Side): string | null {
  return side === "over" ? prop.book_over : prop.book_under;
}

export function sideEdge(prop: Prop, side: Side): number | null {
  return side === "over" ? prop.edge_over : prop.edge_under;
}

export function sideModelProb(prop: Prop, side: Side): number {
  return side === "over" ? prop.model_prob_over : prop.model_prob_under;
}

export function sideImpliedProb(prop: Prop, side: Side): number | null {
  return side === "over" ? prop.implied_prob_over : prop.implied_prob_under;
}

// Mirrors scripts/common.py's pick_units -- profit/loss in units for a
// flat 1-unit bet at this price, or null if the price is unknown.
export function pickUnits(price: number | null, hit: boolean): number | null {
  if (price === null) return null;
  if (!hit) return -1;
  return price > 0 ? price / 100 : 100 / -price;
}

// Mirrors scripts/common.py's prob_to_american -- the no-vig American odds
// a probability implies, e.g. 50% -> -100, 40% -> +150.
export function probToAmericanOdds(p: number | null): number | null {
  if (p === null || Number.isNaN(p)) return null;
  const clamped = Math.min(Math.max(p, 0.01), 0.99);
  return clamped >= 0.5
    ? Math.round((-100 * clamped) / (1 - clamped))
    : Math.round((100 * (1 - clamped)) / clamped);
}
