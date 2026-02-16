export type Sport = 'NBA' | 'NFL' | 'NHL' | 'MLB' | 'NCAAB' | 'NCAAF';

export interface Team {
  id: number;
  external_id: string;
  sport: string;
  name: string;
  abbreviation: string;
  city: string;
  conference: string;
  division: string;
  logo_url: string;
  current_elo: number;
}

export interface GameTeam {
  id: number;
  name: string;
  abbreviation: string;
  logo_url: string;
  current_elo: number;
}

export interface PredictionSummary {
  win_probability: number;
  predicted_winner_id: number;
  predicted_home_score: number;
  predicted_away_score: number;
  confidence: number;
}

export interface Game {
  id: number;
  external_id: string;
  sport: string;
  season: number;
  game_date: string;
  status: string;
  is_postseason: boolean;
  home_team: GameTeam;
  away_team: GameTeam;
  home_score: number | null;
  away_score: number | null;
  prediction: PredictionSummary | null;
}

export interface GameListResponse {
  games: Game[];
  total: number;
}

export interface Factor {
  factor: string;
  impact: number;
  direction: string;
  detail: string;
}

export interface QuarterPredictions {
  home: number[];
  away: number[];
}

export interface PredictionDetail {
  id: number;
  win_probability: number;
  confidence: number;
  predicted_winner_id: number;
  predicted_home_score: number;
  predicted_away_score: number;
  predicted_spread: number;
  predicted_total: number;
  quarter_predictions: QuarterPredictions | null;
  key_factors: Factor[];
}

export interface HeadToHeadGame {
  game_date: string;
  home_team_abbreviation: string;
  away_team_abbreviation: string;
  home_score: number;
  away_score: number;
  winner_abbreviation: string;
}

export interface TeamComparisonStat {
  stat_name: string;
  home_value: number;
  away_value: number;
}

export interface GameDetail {
  id: number;
  external_id: string;
  sport: string;
  season: number;
  game_date: string;
  status: string;
  is_postseason: boolean;
  home_team: Team;
  away_team: Team;
  home_score: number | null;
  away_score: number | null;
  home_period_scores: number[] | null;
  away_period_scores: number[] | null;
  predictions: PredictionDetail[];
  head_to_head: HeadToHeadGame[];
  team_comparison: TeamComparisonStat[];
}

export interface AccuracyOverview {
  total_predictions: number;
  correct_predictions: number;
  accuracy_pct: number;
  avg_score_error: number;
  avg_spread_error: number;
  games_predicted: number;
  model_accuracy: number | null;
}

export interface AccuracyBySportItem {
  sport: string;
  total: number;
  correct: number;
  accuracy_pct: number;
  model_accuracy: number | null;
}

export interface AccuracyByTypeItem {
  prediction_type: string;
  accuracy_pct: number;
  avg_error: number;
}

export interface AccuracyTrendPoint {
  date: string;
  accuracy_pct: number;
  total: number;
}

export interface RecentPredictionResult {
  game_id: number;
  game_date: string;
  home_team: string;
  away_team: string;
  predicted_winner: string;
  actual_winner: string;
  was_correct: boolean;
  predicted_score: string;
  actual_score: string;
  score_error: number;
}

export interface EloHistoryPoint {
  game_date: string;
  elo_before: number;
  elo_after: number;
}

export interface CalibrationBucket {
  bucket_label: string;
  bucket_midpoint: number;
  correct: number;
  total: number;
  accuracy_pct: number;
}

export interface CalibrationSportData {
  sport: string;
  overall_correct: number;
  overall_total: number;
  overall_accuracy_pct: number;
  buckets: CalibrationBucket[];
}

export interface CalibrationResponse {
  sports: CalibrationSportData[];
}
