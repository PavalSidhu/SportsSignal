import type {
  AccuracyBySportItem,
  AccuracyByTypeItem,
  AccuracyOverview,
  AccuracyTrendPoint,
  CalibrationResponse,
  GameDetail,
  GameListResponse,
  RecentPredictionResult,
  Team,
} from '../types';
import { api } from './client';

export function fetchGames(params: {
  sport: string;
  date?: string;
  status?: string;
  limit?: number;
  offset?: number;
}): Promise<GameListResponse> {
  const search = new URLSearchParams();
  search.set('sport', params.sport);
  if (params.date) search.set('date', params.date);
  if (params.status) search.set('status', params.status);
  search.set('limit', String(params.limit ?? 200));
  if (params.offset) search.set('offset', String(params.offset));
  const tzOffset = -(new Date().getTimezoneOffset() / 60);
  search.set('tz_offset', String(tzOffset));
  return api.get(`/api/v1/games?${search}`);
}

export function fetchGameDetail(id: number): Promise<GameDetail> {
  return api.get(`/api/v1/games/${id}`);
}

export function fetchTeams(sport: string): Promise<Team[]> {
  return api.get(`/api/v1/teams?sport=${sport}`);
}

export function fetchAccuracyOverview(sport?: string): Promise<AccuracyOverview> {
  const search = sport ? `?sport=${sport}` : '';
  return api.get(`/api/v1/accuracy${search}`);
}

export function fetchAccuracyBySport(): Promise<{ by_sport: AccuracyBySportItem[] }> {
  return api.get('/api/v1/accuracy/by-sport');
}

export function fetchAccuracyByType(sport?: string): Promise<{ by_type: AccuracyByTypeItem[] }> {
  const search = sport ? `?sport=${sport}` : '';
  return api.get(`/api/v1/accuracy/by-type${search}`);
}

export function fetchAccuracyTrend(sport?: string): Promise<{ trend: AccuracyTrendPoint[] }> {
  const search = sport ? `?sport=${sport}` : '';
  return api.get(`/api/v1/accuracy/trend${search}`);
}

export function fetchRecentPredictions(
  sport?: string,
  limit = 20
): Promise<RecentPredictionResult[]> {
  const search = new URLSearchParams();
  if (sport) search.set('sport', sport);
  search.set('limit', String(limit));
  return api.get(`/api/v1/accuracy/recent?${search}`);
}

export function fetchCalibration(): Promise<CalibrationResponse> {
  return api.get('/api/v1/accuracy/calibration');
}
