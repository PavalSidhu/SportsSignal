import { useQuery } from '@tanstack/react-query';
import { fetchGameDetail, fetchGames } from '../../api/endpoints';
import { queryKeys } from './keys';

export function useGames(params: { sport: string; date?: string }) {
  return useQuery({
    queryKey: queryKeys.games.list(params),
    queryFn: () => fetchGames(params),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
  });
}

export function useGameDetail(id: number) {
  return useQuery({
    queryKey: queryKeys.games.detail(id),
    queryFn: () => fetchGameDetail(id),
    staleTime: 5 * 60 * 1000,
    refetchOnWindowFocus: false,
    enabled: id > 0,
  });
}
