export type Side = "over" | "under";
export type Confidence = "Low" | "Medium" | "High";

export interface RecentGame {
  date: string;
  opponent: string;
  home: boolean;
  shots: number;
  toi: number | null;
}

export interface Prop {
  player_id: number;
  player_name: string;
  position: string;
  team: string;
  opponent: string;
  home: boolean;
  game_id: number;
  matchup: string;
  start_time_utc: string | null;
  line: number;
  price_over: number | null;
  price_under: number | null;
  book_over: string | null;
  book_under: string | null;
  raw_model_prob_over: number;
  raw_model_prob_under: number;
  model_prob_over: number;
  model_prob_under: number;
  implied_prob_over: number | null;
  implied_prob_under: number | null;
  edge_over: number | null;
  edge_under: number | null;
  recommended_side: Side;
  recommended_edge: number;
  projected_sog: number;
  season_avg_sog: number | null;
  avg_toi: number | null;
  shots_per_60: number | null;
  opponent_factor: number;
  dispersion: number;
  sample_games: number;
  season_games: number;
  confidence: Confidence;
  // Signals behind the confidence tier, supporting ones first.
  confidence_reasons: { text: string; supports: boolean }[];
  trends: string[];
  recent_games: RecentGame[];
}

export interface Meta {
  generated_at: string;
  slate_date: string | null;
  season: number | null;
  game_count: number;
  odds_source: "live" | "sample";
  odds_fetched_at: string | null;
  prop_count: number;
  inactive_players_excluded: number;
  model_weight: number;
  matchups: string[];
  books: string[];
}

export interface HitRateSummary {
  picks: number;
  hits: number;
  hit_rate: number;
  // Profit/loss for a flat 1-unit bet on every pick at the price it was
  // recommended at; null when no pick in the slice has a recorded price.
  units: number | null;
  priced_picks: number;
  pushes: number;
}

export interface TrackRecord {
  overall: HitRateSummary | null;
  by_confidence: Partial<Record<Confidence, HitRateSummary>>;
  by_side: Partial<Record<Side, HitRateSummary>>;
  days_graded: number;
  updated_at: string;
}

export interface GradedPick {
  date: string;
  player_name: string;
  position: string;
  team: string;
  opponent: string;
  line: number;
  side: Side;
  confidence: Confidence;
  edge: number;
  price: number | null;
  actual: number;
  result: "win" | "loss" | "push";
}

export interface TrackRecordDetail {
  updated_at: string;
  picks: GradedPick[];
}
