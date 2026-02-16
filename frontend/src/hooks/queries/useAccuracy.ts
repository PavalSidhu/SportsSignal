import { useQuery } from '@tanstack/react-query';
import {
  fetchAccuracyBySport,
  fetchAccuracyByType,
  fetchAccuracyOverview,
  fetchAccuracyTrend,
  fetchCalibration,
  fetchRecentPredictions,
} from '../../api/endpoints';
import { queryKeys } from './keys';

export function useAccuracyOverview(sport?: string) {
  return useQuery({
    queryKey: queryKeys.accuracy.overview(sport),
    queryFn: () => fetchAccuracyOverview(sport),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useAccuracyBySport() {
  return useQuery({
    queryKey: queryKeys.accuracy.bySport(),
    queryFn: fetchAccuracyBySport,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useAccuracyByType(sport?: string) {
  return useQuery({
    queryKey: queryKeys.accuracy.byType(sport),
    queryFn: () => fetchAccuracyByType(sport),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useAccuracyTrend(sport?: string) {
  return useQuery({
    queryKey: queryKeys.accuracy.trend(sport),
    queryFn: () => fetchAccuracyTrend(sport),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useRecentPredictions(sport?: string) {
  return useQuery({
    queryKey: queryKeys.accuracy.recent(sport),
    queryFn: () => fetchRecentPredictions(sport),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useCalibration() {
  return useQuery({
    queryKey: queryKeys.accuracy.calibration(),
    queryFn: fetchCalibration,
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}
